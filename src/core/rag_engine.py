"""
rag_engine.py — Phase 2: RAG Pipeline cho Q&A Pháp luật
Retrieve → Re-rank → Generate Answer with Citations
"""

import logging
from typing import List, Dict, Optional, Any
from src.database.database import get_db
from src.config import RAG_TOP_K_RETRIEVE, RAG_TOP_K_CONTEXT

logger = logging.getLogger(__name__)


def retrieve_context(
    question: str,
    top_k: int = RAG_TOP_K_RETRIEVE,
) -> List[Dict]:
    """
    Retrieve relevant chunks cho câu hỏi.
    Kết hợp: Hybrid search (BM25 + Vector) + Wiki search
    """
    chunks = []

    # ── 1. Vector Search (nếu có) ──
    try:
        from src.core.embedding_service import vector_search as qdrant_search
        vector_results = qdrant_search(query=question, top_k=top_k)
        for result in vector_results:
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

    # ── 2. FTS5 Chunk Search ──
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

    # ── 3. Deduplicate & Merge ──
    seen_chunks = set()
    unique_chunks = []
    for chunk in chunks:
        key = (chunk["document_id"], chunk.get("dieu"), chunk.get("khoan"))
        if key not in seen_chunks:
            seen_chunks.add(key)
            unique_chunks.append(chunk)

    # ── 4. Sort by score (higher = better) ──
    unique_chunks.sort(key=lambda x: x.get("score", 0), reverse=True)

    return unique_chunks[:top_k]


def enrich_chunks_with_metadata(chunks: List[Dict]) -> List[Dict]:
    """Bổ sung metadata từ documents vào chunks."""
    if not chunks:
        return chunks

    doc_ids = list(set(c["document_id"] for c in chunks if c.get("document_id")))
    if not doc_ids:
        return chunks

    with get_db() as conn:
        placeholders = ",".join("?" * len(doc_ids))
        docs = conn.execute(
            f"SELECT id, doc_number, title, doc_type, effectiveness_status, issuing_date, issuing_authority FROM documents WHERE id IN ({placeholders})",
            doc_ids
        ).fetchall()
        doc_map = {d["id"]: dict(d) for d in docs}

    for chunk in chunks:
        doc_id = chunk.get("document_id")
        if doc_id and doc_id in doc_map:
            doc = doc_map[doc_id]
            chunk["doc_number"] = doc.get("doc_number", "")
            chunk["doc_title"] = doc.get("title", "")
            chunk["doc_type"] = doc.get("doc_type", "")
            chunk["effectiveness_status"] = doc.get("effectiveness_status", "")
            chunk["issuing_date"] = doc.get("issuing_date", "")
            chunk["issuing_authority"] = doc.get("issuing_authority", "")

    return chunks


def rerank_chunks(question: str, chunks: List[Dict], top_k: int = RAG_TOP_K_CONTEXT) -> List[Dict]:
    """
    Re-rank chunks sử dụng cross-encoder (tùy chọn).
    Nếu cross-encoder không khả dụng, dùng simple scoring.
    """
    if not chunks:
        return []

    # Simple re-ranking: ưu tiên văn bản còn hiệu lực
    from src.config import EFFECTIVENESS_BOOST

    for chunk in chunks:
        base_score = chunk.get("score", 0)
        eff_status = chunk.get("effectiveness_status", "con_hieu_luc")
        boost = EFFECTIVENESS_BOOST.get(eff_status, 1.0)

        # Boost theo loại văn bản (Ưu tiên Luật/Bộ luật hơn là Thông tư/Nghị định)
        type_boost = 1.0
        doc_type = chunk.get("doc_type", "")
        if doc_type in ["luat", "bo_luat"]:
            type_boost = 1.5
        elif doc_type == "nghi_dinh":
            type_boost = 1.2

        # Boost cho chunks có Điều/Khoản cụ thể
        specificity_boost = 1.0
        if chunk.get("dieu"):
            specificity_boost += 0.2
        if chunk.get("khoan"):
            specificity_boost += 0.1

        chunk["rerank_score"] = base_score * boost * type_boost * specificity_boost

    # Sort
    chunks.sort(key=lambda x: x.get("rerank_score", 0), reverse=True)
    return chunks[:top_k]


def ask_question(
    question: str,
    chat_history: Optional[List[Dict]] = None,
    top_k_retrieve: int = RAG_TOP_K_RETRIEVE,
    top_k_context: int = RAG_TOP_K_CONTEXT,
) -> Dict:
    """
    Pipeline RAG hoàn chỉnh:
    1. Retrieve relevant chunks
    2. Enrich with metadata
    3. Re-rank
    4. Generate answer with citations
    """
    from src.core.ai_service import generate_qa_answer, is_ai_available

    # Step 1: Retrieve
    raw_chunks = retrieve_context(question, top_k=top_k_retrieve)

    # Step 2: Enrich
    enriched_chunks = enrich_chunks_with_metadata(raw_chunks)

    # Step 3: Re-rank
    context_chunks = rerank_chunks(question, enriched_chunks, top_k=top_k_context)

    # Nếu không tìm được context nào
    if not context_chunks:
        return {
            "question": question,
            "answer": "Không tìm thấy quy định pháp luật liên quan trong cơ sở dữ liệu. Vui lòng thử diễn đạt lại câu hỏi hoặc sử dụng từ khóa cụ thể hơn.",
            "citations": [],
            "model": "",
            "chunks_used": 0,
            "ai_available": is_ai_available(),
        }

    # Step 4: Generate answer
    if is_ai_available():
        result = generate_qa_answer(
            question=question,
            context_chunks=context_chunks,
            chat_history=chat_history,
        )
    else:
        # Fallback: Hiển thị context chunks trực tiếp
        answer_parts = ["**Các quy định liên quan tìm được:**\n"]
        for i, chunk in enumerate(context_chunks, 1):
            header = f"**[{i}]**"
            if chunk.get("doc_number"):
                header += f" {chunk['doc_number']}"
            if chunk.get("dieu"):
                header += f" — Điều {chunk['dieu']}"
            if chunk.get("khoan"):
                header += f", Khoản {chunk['khoan']}"
            answer_parts.append(f"{header}\n{chunk['content'][:500]}\n")

        answer_parts.append("\n*⚠️ AI không khả dụng. Vui lòng cấu hình API key (OPENAI_API_KEY hoặc ANTHROPIC_API_KEY) để có câu trả lời tổng hợp.*")

        result = {
            "answer": "\n".join(answer_parts),
            "citations": [],
            "model": "none (fallback)",
            "chunks_used": len(context_chunks),
        }

    result["question"] = question
    result["ai_available"] = is_ai_available()
    return result


def get_suggested_questions() -> List[str]:
    """Gợi ý câu hỏi mẫu cho người dùng."""
    return [
        "Điều kiện chuyển nhượng quyền sử dụng đất?",
        "Thủ tục thành lập doanh nghiệp theo quy định mới nhất?",
        "Quy định về thời giờ làm việc, nghỉ ngơi?",
        "Điều kiện cấp giấy phép xây dựng?",
        "Quy định xử phạt vi phạm giao thông?",
        "Thuế thu nhập cá nhân áp dụng cho lương?",
    ]
