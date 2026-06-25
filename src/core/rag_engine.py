"""
rag_engine.py — Phase 2: RAG Pipeline cho Q&A Pháp luật
LangGraph StateGraph: Retrieve → Re-rank → Generate Answer with Citations
"""

import logging
from typing import List, Dict, Optional, TypedDict, AsyncGenerator

from langgraph.graph import StateGraph, END

from src.database.database import get_db
from src.config import RAG_TOP_K_RETRIEVE, RAG_TOP_K_CONTEXT, HIERARCHY_LABELS, EFFECTIVENESS_LABELS

logger = logging.getLogger(__name__)


from src.core.guard_nodes import (
    security_guard_node,
    intent_router_node,
    _route_by_intent,
    small_talk_response_node,
    out_of_scope_response_node,
    blocked_response_node,
)


# ── State Definition ──────────────────────────────────────────────────────────

class RAGState(TypedDict, total=False):
    question: str
    session_id: Optional[str]
    chat_history: List[Dict]
    session_summary: Optional[str]
    # Guard & Router fields (thêm mới)
    blocked: bool
    threat_type: Optional[str]
    intent: str
    # RAG pipeline fields
    raw_chunks: List[Dict]
    enriched_chunks: List[Dict]
    reranked_chunks: List[Dict]
    expanded_chunks: List[Dict]
    tagged_chunks: List[Dict]
    answer: str
    citations: List[Dict]
    model: str
    chunks_used: int
    ai_available: bool
    error: Optional[str]


# ── Helper Functions (giữ nguyên logic cũ) ───────────────────────────────────

def retrieve_context(question: str, top_k: int = RAG_TOP_K_RETRIEVE) -> List[Dict]:
    """Hybrid search: Vector (Qdrant) + BM25 (FTS5) + dedup + sort."""
    chunks = []

    try:
        from src.core.embedding_service import vector_search as qdrant_search
        for result in qdrant_search(query=question, top_k=top_k):
            payload = result["payload"]
            chunks.append({
                "chunk_id": result["id"],
                "document_id": payload.get("document_id"),
                "content": payload.get("content_preview", ""),
                "dieu": payload.get("dieu"),
                "khoan": payload.get("khoan"),
                "chuong": payload.get("chuong"),
                "score": result["score"],
                "source": "vector",
            })
    except Exception as e:
        logger.warning(f"[RAG] Vector search failed: {e}")

    try:
        from src.services.search import _build_fts_query
        fts_q = _build_fts_query(question)
        with get_db() as conn:
            rows = conn.execute("""
                SELECT c.id, c.document_id, c.content, c.dieu, c.khoan, c.chuong,
                       bm25(chunks_fts) AS score
                FROM chunks_fts
                JOIN chunks c ON chunks_fts.rowid = c.id
                WHERE chunks_fts MATCH ?
                ORDER BY score
                LIMIT ?
            """, (fts_q, top_k)).fetchall()
            for row in rows:
                r = dict(row)
                chunks.append({
                    "chunk_id": r["id"],
                    "document_id": r["document_id"],
                    "content": r["content"],
                    "dieu": r.get("dieu"),
                    "khoan": r.get("khoan"),
                    "chuong": r.get("chuong"),
                    "score": abs(float(r.get("score", 0))),
                    "source": "bm25",
                })
    except Exception as e:
        logger.warning(f"[RAG] FTS5 search failed: {e}")

    seen = set()
    unique = []
    for c in chunks:
        key = (c["document_id"], c.get("dieu"), c.get("khoan"))
        if key not in seen:
            seen.add(key)
            unique.append(c)
    unique.sort(key=lambda x: x.get("score", 0), reverse=True)
    return unique[:top_k]


def enrich_chunks_with_metadata(chunks: List[Dict]) -> List[Dict]:
    """Bổ sung metadata từ bảng documents vào chunks."""
    if not chunks:
        return chunks
    doc_ids = list(set(c["document_id"] for c in chunks if c.get("document_id")))
    if not doc_ids:
        return chunks
    with get_db() as conn:
        placeholders = ",".join("?" * len(doc_ids))
        docs = conn.execute(
            f"SELECT id, doc_number, title, doc_type, effectiveness_status, issuing_date, issuing_authority FROM documents WHERE id IN ({placeholders})",
            doc_ids,
        ).fetchall()
        doc_map = {d["id"]: dict(d) for d in docs}
    for chunk in chunks:
        doc = doc_map.get(chunk.get("document_id"), {})
        chunk.update({
            "doc_number": doc.get("doc_number", ""),
            "doc_title": doc.get("title", ""),
            "doc_type": doc.get("doc_type", ""),
            "effectiveness_status": doc.get("effectiveness_status", ""),
            "issuing_date": doc.get("issuing_date", ""),
            "issuing_authority": doc.get("issuing_authority", ""),
        })
    return chunks


def rerank_chunks(chunks: List[Dict], top_k: int = RAG_TOP_K_CONTEXT) -> List[Dict]:
    """Re-rank theo effectiveness, doc_type hierarchy, và specificity."""
    if not chunks:
        return []
    from src.config import EFFECTIVENESS_BOOST
    for chunk in chunks:
        base = chunk.get("score", 0)
        eff_boost = EFFECTIVENESS_BOOST.get(chunk.get("effectiveness_status", "con_hieu_luc"), 1.0)
        rank, _ = HIERARCHY_LABELS.get(chunk.get("doc_type", ""), (5, ""))
        type_boost = 1.0 + (rank / 30.0)  # rank 15 → 1.5, rank 1 → 1.03
        spec_boost = 1.0 + (0.2 if chunk.get("dieu") else 0) + (0.1 if chunk.get("khoan") else 0)
        chunk["rerank_score"] = base * eff_boost * type_boost * spec_boost
    chunks.sort(key=lambda x: x.get("rerank_score", 0), reverse=True)
    return chunks[:top_k]


def expand_context_with_guidance(chunks: List[Dict]) -> List[Dict]:
    """Tìm thêm các văn bản hướng dẫn thi hành (relation_type = 'huong_dan')."""
    if not chunks:
        return chunks
    doc_ids = list(set(c["document_id"] for c in chunks if c.get("document_id")))
    if not doc_ids:
        return chunks
    guiding_docs = []
    try:
        with get_db() as conn:
            placeholders = ",".join("?" * len(doc_ids))
            rows = conn.execute(
                f"SELECT target_doc_id FROM doc_relations WHERE source_doc_id IN ({placeholders}) AND relation_type = 'huong_dan' AND target_doc_id IS NOT NULL",
                doc_ids,
            ).fetchall()
            guiding_docs = [r["target_doc_id"] for r in rows]
    except Exception as e:
        logger.warning(f"[RAG] Context expansion failed: {e}")
        return chunks

    if not guiding_docs:
        return chunks

    expanded = list(chunks)
    added = 0
    try:
        with get_db() as conn:
            placeholders = ",".join("?" * len(guiding_docs))
            rows = conn.execute(
                f"SELECT c.*, d.doc_number, d.title as doc_title, d.doc_type, d.effectiveness_status FROM chunks c JOIN documents d ON c.document_id = d.id WHERE c.document_id IN ({placeholders})",
                guiding_docs,
            ).fetchall()
            for r in rows:
                c = dict(r)
                c["source"] = "context_expansion"
                if not any(x["document_id"] == c["document_id"] and x.get("dieu") == c.get("dieu") for x in expanded):
                    expanded.append(c)
                    added += 1
                    if added >= 4:
                        break
    except Exception as e:
        logger.warning(f"[RAG] Failed to load guiding chunks: {e}")

    logger.info(f"[RAG] Context expansion added {added} guiding chunks")
    return expanded


# ── LangGraph Nodes ───────────────────────────────────────────────────────────

def load_session_node(state: RAGState) -> RAGState:
    """Load lịch sử chat và session summary từ database."""
    session_id = state.get("session_id")
    if not session_id:
        return state
    try:
        from src.services.chat_service import get_session_detail, get_chat_messages
        session_detail = get_session_detail(session_id)
        if session_detail:
            state["session_summary"] = session_detail.get("summary")
        db_messages = get_chat_messages(session_id)
        state["chat_history"] = [
            {"role": m["role"], "content": m["content"]}
            for m in db_messages
            if m["role"] in ("user", "assistant")
        ][-10:]
    except Exception as e:
        logger.warning(f"[RAG] Failed to load session context: {e}")
    return state


def retrieve_node(state: RAGState) -> RAGState:
    """Node: Hybrid search để lấy raw chunks."""
    state["raw_chunks"] = retrieve_context(state["question"], top_k=RAG_TOP_K_RETRIEVE)
    return state


def _should_generate(state: RAGState) -> str:
    """Conditional edge: có chunks hay không."""
    return "enrich" if state.get("raw_chunks") else "fallback"


def enrich_node(state: RAGState) -> RAGState:
    """Node: Thêm metadata document vào chunks."""
    state["enriched_chunks"] = enrich_chunks_with_metadata(state.get("raw_chunks", []))
    return state


def rerank_node(state: RAGState) -> RAGState:
    """Node: Re-rank và lọc chunks."""
    state["reranked_chunks"] = rerank_chunks(
        state.get("enriched_chunks", []),
        top_k=RAG_TOP_K_CONTEXT,
    )
    return state


def tag_chunks(chunks: List[Dict]) -> List[Dict]:
    """Gắn tag thứ bậc + hiệu lực vào mỗi chunk để LLM không cần tự suy luận."""
    tagged = []
    for chunk in chunks:
        doc_type = chunk.get("doc_type", "")
        eff = chunk.get("effectiveness_status", "")
        rank, type_name = HIERARCHY_LABELS.get(doc_type, (9, doc_type.upper() or "VĂN BẢN"))
        eff_icon = EFFECTIVENESS_LABELS.get(eff, "⚪")
        chunk = dict(chunk)
        chunk["_tag"] = f"[{eff_icon} | {type_name} | Hiệu lực pháp lý: {rank}/15]"
        tagged.append(chunk)
    return tagged


def tag_node(state: RAGState) -> RAGState:
    """Node: Gắn tag thứ bậc + hiệu lực vào chunks để LLM đọc trực tiếp, không cần suy luận."""
    state["tagged_chunks"] = tag_chunks(state.get("expanded_chunks", []))
    return state


def expand_node(state: RAGState) -> RAGState:
    """Node: Mở rộng context với văn bản hướng dẫn thi hành."""
    try:
        state["expanded_chunks"] = expand_context_with_guidance(state.get("reranked_chunks", []))
    except Exception as e:
        logger.warning(f"[RAG] expand_node error: {e}")
        state["expanded_chunks"] = state.get("reranked_chunks", [])
    return state


def generate_node(state: RAGState) -> RAGState:
    """Node: Gọi LLM sinh câu trả lời từ context."""
    from src.core.ai_service import generate_qa_answer, is_ai_available
    context_chunks = state.get("tagged_chunks", [])
    if is_ai_available():
        result = generate_qa_answer(
            question=state["question"],
            context_chunks=context_chunks,
            chat_history=state.get("chat_history"),
            summary=state.get("session_summary"),
        )
    else:
        parts = ["**Các quy định liên quan tìm được:**\n"]
        for i, chunk in enumerate(context_chunks, 1):
            header = f"**[{i}]** {chunk.get('doc_number', '')}"
            if chunk.get("dieu"):
                header += f" — Điều {chunk['dieu']}"
            parts.append(f"{header}\n{chunk['content'][:500]}\n")
        parts.append("\n*⚠️ AI không khả dụng. Vui lòng cấu hình API key.*")
        result = {"answer": "\n".join(parts), "citations": [], "model": "none (fallback)", "chunks_used": len(context_chunks)}

    state.update({
        "answer": result["answer"],
        "citations": result.get("citations", []),
        "model": result.get("model", ""),
        "chunks_used": result.get("chunks_used", len(context_chunks)),
        "ai_available": is_ai_available(),
    })
    return state


def fallback_node(state: RAGState) -> RAGState:
    """Node: Trả về khi không tìm thấy context nào."""
    from src.core.ai_service import is_ai_available
    state.update({
        "answer": "Không tìm thấy quy định pháp luật liên quan trong cơ sở dữ liệu. Vui lòng thử diễn đạt lại câu hỏi hoặc sử dụng từ khóa cụ thể hơn.",
        "citations": [],
        "model": "",
        "chunks_used": 0,
        "ai_available": is_ai_available(),
    })
    return state


def save_session_node(state: RAGState) -> RAGState:
    """Node: Lưu messages vào database."""
    session_id = state.get("session_id")
    if not session_id:
        return state
    try:
        from src.services.chat_service import save_chat_message
        save_chat_message(session_id, "user", state["question"])
        save_chat_message(session_id, "assistant", state.get("answer", ""))
    except Exception as e:
        logger.warning(f"[RAG] Failed to save conversation: {e}")
    return state


# ── Build LangGraph App ───────────────────────────────────────────────────────

def _build_rag_graph() -> StateGraph:
    graph = StateGraph(RAGState)

    # ── Guard & Router Nodes (mới) ─────────────────────────────────────────────
    graph.add_node("security_guard", security_guard_node)
    graph.add_node("intent_router", intent_router_node)
    graph.add_node("small_talk_response", small_talk_response_node)
    graph.add_node("out_of_scope_response", out_of_scope_response_node)
    graph.add_node("blocked_response", blocked_response_node)

    # ── RAG Pipeline Nodes (giữ nguyên) ──────────────────────────────────────
    graph.add_node("load_session", load_session_node)
    graph.add_node("retrieve", retrieve_node)
    graph.add_node("enrich", enrich_node)
    graph.add_node("rerank", rerank_node)
    graph.add_node("expand", expand_node)
    graph.add_node("tag", tag_node)
    graph.add_node("generate", generate_node)
    graph.add_node("fallback", fallback_node)
    graph.add_node("save_session", save_session_node)

    # ── Edges ─────────────────────────────────────────────────────────────────
    # Entry: security_guard → intent_router → conditional routing
    graph.set_entry_point("security_guard")
    graph.add_edge("security_guard", "intent_router")
    graph.add_conditional_edges(
        "intent_router",
        _route_by_intent,
        {
            "load_session": "load_session",   # → RAG pipeline
            "small_talk": "small_talk_response",
            "out_of_scope": "out_of_scope_response",
            "blocked_response": "blocked_response",
        },
    )

    # Short-circuit: các intent không cần RAG → thẳng save_session
    graph.add_edge("small_talk_response", "save_session")
    graph.add_edge("out_of_scope_response", "save_session")
    graph.add_edge("blocked_response", "save_session")

    # RAG pipeline (giữ nguyên flow cũ)
    graph.add_edge("load_session", "retrieve")
    graph.add_conditional_edges("retrieve", _should_generate, {"enrich": "enrich", "fallback": "fallback"})
    graph.add_edge("enrich", "rerank")
    graph.add_edge("rerank", "expand")
    graph.add_edge("expand", "tag")
    graph.add_edge("tag", "generate")
    graph.add_edge("generate", "save_session")
    graph.add_edge("fallback", "save_session")
    graph.add_edge("save_session", END)
    return graph.compile()


_rag_app = None


def _get_rag_app():
    global _rag_app
    if _rag_app is None:
        _rag_app = _build_rag_graph()
    return _rag_app


# ── Public API (giữ nguyên signature) ────────────────────────────────────────

def ask_question(
    question: str,
    session_id: Optional[str] = None,
    chat_history: Optional[List[Dict]] = None,
) -> Dict:
    """Pipeline RAG hoàn chỉnh qua LangGraph StateGraph."""
    app = _get_rag_app()
    initial_state: RAGState = {
        "question": question,
        "session_id": session_id,
        "chat_history": chat_history or [],
        "session_summary": None,
    }
    final_state = app.invoke(initial_state)
    return {
        "question": question,
        "answer": final_state.get("answer", ""),
        "citations": final_state.get("citations", []),
        "model": final_state.get("model", ""),
        "chunks_used": final_state.get("chunks_used", 0),
        "ai_available": final_state.get("ai_available", False),
        "session_id": session_id,
    }


async def ask_question_stream(
    question: str,
    session_id: Optional[str] = None,
) -> AsyncGenerator[Dict, None]:
    """
    Streaming version: yield từng update của RAG graph dưới dạng SSE events.
    Dùng cho endpoint GET /api/qa/stream.
    """
    app = _get_rag_app()
    initial_state: RAGState = {
        "question": question,
        "session_id": session_id,
        "chat_history": [],
        "session_summary": None,
    }
    async for event in app.astream(initial_state):
        node_name = list(event.keys())[0] if event else "unknown"
        node_state = event.get(node_name, {})
        if node_name == "generate" and "answer" in node_state:
            yield {"type": "answer", "content": node_state["answer"], "citations": node_state.get("citations", [])}
        elif node_name == "fallback" and "answer" in node_state:
            yield {"type": "answer", "content": node_state["answer"], "citations": []}
        else:
            yield {"type": "progress", "node": node_name}


def get_suggested_questions() -> List[str]:
    return [
        "Điều kiện chuyển nhượng quyền sử dụng đất?",
        "Thủ tục thành lập doanh nghiệp theo quy định mới nhất?",
        "Quy định về thời giờ làm việc, nghỉ ngơi?",
        "Điều kiện cấp giấy phép xây dựng?",
        "Quy định xử phạt vi phạm giao thông?",
        "Thuế thu nhập cá nhân áp dụng cho lương?",
    ]
