"""
rag_engine.py — Phase 2: RAG Pipeline cho Q&A Pháp luật
LangGraph StateGraph: Retrieve → Re-rank → Generate Answer with Citations
"""

import logging
import json
from typing import List, Dict, Optional, Any, TypedDict, AsyncGenerator

from langgraph.graph import StateGraph, END

from src.database.database import get_db
from src.config import RAG_TOP_K_RETRIEVE, RAG_TOP_K_CONTEXT

logger = logging.getLogger(__name__)


# ── State Definition ──────────────────────────────────────────────────────────

class RAGState(TypedDict, total=False):
    question: str
    session_id: Optional[str]
    chat_history: List[Dict]
    session_summary: Optional[str]
    raw_chunks: List[Dict]
    enriched_chunks: List[Dict]
    reranked_chunks: List[Dict]
    expanded_chunks: List[Dict]
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


def rerank_chunks(question: str, chunks: List[Dict], top_k: int = RAG_TOP_K_CONTEXT) -> List[Dict]:
    """Re-rank theo effectiveness, doc_type hierarchy, và specificity."""
    if not chunks:
        return []
    from src.config import EFFECTIVENESS_BOOST
    for chunk in chunks:
        base = chunk.get("score", 0)
        eff_boost = EFFECTIVENESS_BOOST.get(chunk.get("effectiveness_status", "con_hieu_luc"), 1.0)
        type_boost = {"luat": 1.5, "bo_luat": 1.5, "nghi_dinh": 1.2}.get(chunk.get("doc_type", ""), 1.0)
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
        state["question"],
        state.get("enriched_chunks", []),
        top_k=RAG_TOP_K_CONTEXT,
    )
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
    context_chunks = state.get("expanded_chunks", [])
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
    graph.add_node("load_session", load_session_node)
    graph.add_node("retrieve", retrieve_node)
    graph.add_node("enrich", enrich_node)
    graph.add_node("rerank", rerank_node)
    graph.add_node("expand", expand_node)
    graph.add_node("generate", generate_node)
    graph.add_node("fallback", fallback_node)
    graph.add_node("save_session", save_session_node)

    graph.set_entry_point("load_session")
    graph.add_edge("load_session", "retrieve")
    graph.add_conditional_edges("retrieve", _should_generate, {"enrich": "enrich", "fallback": "fallback"})
    graph.add_edge("enrich", "rerank")
    graph.add_edge("rerank", "expand")
    graph.add_edge("expand", "generate")
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
    top_k_retrieve: int = RAG_TOP_K_RETRIEVE,
    top_k_context: int = RAG_TOP_K_CONTEXT,
) -> Dict:
    """
    Pipeline RAG hoàn chỉnh qua LangGraph StateGraph.
    Signature giữ nguyên để không break main.py.
    """
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
