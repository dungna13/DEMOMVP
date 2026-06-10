"""
vector_search.py — Phase 2: Hybrid Search (BM25 + Vector + RRF)
Kết hợp full-text search từ FTS5 và vector search từ Qdrant
"""

import logging
from typing import Optional, List, Dict, Any
from src.config import RRF_K, RRF_WEIGHTS, EFFECTIVENESS_BOOST
from src.database.database import get_db

logger = logging.getLogger(__name__)


def _rrf_score(rank: int, k: int = RRF_K) -> float:
    """Reciprocal Rank Fusion score cho 1 document tại rank."""
    return 1.0 / (k + rank)


def _detect_search_mode(query: str) -> str:
    """
    Phát hiện loại truy vấn để chọn trọng số RRF phù hợp.
    - keyword: Tra cứu theo số hiệu/tiêu đề cụ thể
    - semantic: Tìm quy định liên quan
    - balanced: Mặc định
    """
    import re
    # Kiểm tra nếu query chứa số hiệu văn bản
    if re.search(r'\d+[/\-]\d+|QĐ|NĐ|TT\-|QH\d+', query, re.IGNORECASE):
        return "keyword"
    # Kiểm tra nếu query là câu hỏi hoặc mô tả
    question_words = ["quy định", "điều kiện", "thủ tục", "quyền", "nghĩa vụ",
                      "như thế nào", "bao gồm", "ai", "khi nào", "ở đâu"]
    if any(w in query.lower() for w in question_words):
        return "semantic"
    return "balanced"


def _fts5_search(
    query: str,
    doc_type: Optional[str] = None,
    issuing_authority: Optional[str] = None,
    year: Optional[int] = None,
    effectiveness_status: Optional[str] = None,
    limit: int = 200,
) -> List[Dict]:
    """
    BM25 search trên SQLite FTS5.
    Returns: list of {doc_id, rank, document_data}
    """
    import re
    from src.services.search import _build_fts_query

    with get_db() as conn:
        filters = []
        params: List[Any] = []

        if doc_type:
            filters.append("d.doc_type = ?")
            params.append(doc_type)
        if issuing_authority:
            filters.append("d.issuing_authority LIKE ?")
            params.append(f"%{issuing_authority}%")
        if year:
            filters.append("(d.issuing_date LIKE ? OR d.issuing_date LIKE ?)")
            params.extend([f"%/{year}", f"{year}%"])
        if effectiveness_status:
            filters.append("d.effectiveness_status = ?")
            params.append(effectiveness_status)

        filter_sql = ("AND " + " AND ".join(filters)) if filters else ""

        q = query.strip()
        if not q:
            return []

        fts_q = _build_fts_query(q)
        sql = f"""
            SELECT
                d.id as doc_id,
                d.*,
                bm25(documents_fts) AS raw_score
            FROM documents_fts
            JOIN documents d ON documents_fts.rowid = d.id
            WHERE documents_fts MATCH ?
            {filter_sql}
            ORDER BY raw_score
            LIMIT ?
        """
        rows = conn.execute(sql, [fts_q] + params + [limit]).fetchall()

        results = []
        for rank, row in enumerate(rows, 1):
            doc = dict(row)
            results.append({
                "doc_id": doc["doc_id"],
                "rank": rank,
                "bm25_score": abs(float(doc.get("raw_score", 0))),
                "document": doc,
            })
        return results


def _vector_search_by_doc(
    query: str,
    doc_type: Optional[str] = None,
    effectiveness_status: Optional[str] = None,
    limit: int = 200,
) -> List[Dict]:
    """
    Vector search trên Qdrant, nhóm theo document_id.
    Returns: list of {doc_id, rank, vector_score, top_chunk}
    """
    try:
        from src.core.embedding_service import vector_search as qdrant_search

        chunk_results = qdrant_search(
            query=query,
            top_k=limit * 3,  # Lấy nhiều chunks, rồi nhóm theo doc
            doc_type=doc_type,
            effectiveness_status=effectiveness_status,
        )

        # Nhóm theo document_id, lấy score cao nhất
        doc_scores: Dict[int, Dict] = {}
        for result in chunk_results:
            doc_id = result["payload"]["document_id"]
            if doc_id not in doc_scores or result["score"] > doc_scores[doc_id]["vector_score"]:
                doc_scores[doc_id] = {
                    "doc_id": doc_id,
                    "vector_score": result["score"],
                    "top_chunk": result["payload"].get("content_preview", ""),
                    "chunk_id": result["id"],
                }

        # Sort by score & assign rank
        sorted_docs = sorted(doc_scores.values(), key=lambda x: x["vector_score"], reverse=True)
        for rank, doc in enumerate(sorted_docs[:limit], 1):
            doc["rank"] = rank

        return sorted_docs[:limit]

    except Exception as e:
        logger.warning(f"[VectorSearch] Fallback to BM25 only: {e}")
        return []


def hybrid_search(
    query: str,
    doc_type: Optional[str] = None,
    issuing_authority: Optional[str] = None,
    year: Optional[int] = None,
    effectiveness_status: Optional[str] = None,
    page: int = 1,
    page_size: int = 10,
    search_mode: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Hybrid Search: BM25 + Vector + RRF Fusion.
    Theo HLD Section 7.4.
    """
    from src.services.search import _highlight, _get_facets

    offset = (page - 1) * page_size
    q = query.strip()
    if not q:
        # Không có query → trả về tất cả (sắp xếp theo ngày)
        from src.services.search import search_documents
        return search_documents(
            query="", doc_type=doc_type, issuing_authority=issuing_authority,
            year=year, effectiveness_status=effectiveness_status,
            page=page, page_size=page_size,
        )

    # Auto-detect search mode
    mode = search_mode or _detect_search_mode(q)
    weights = RRF_WEIGHTS.get(mode, RRF_WEIGHTS["balanced"])
    w_bm25 = weights["bm25"]
    w_vector = weights["vector"]

    # ── BM25 Search ──
    bm25_results = _fts5_search(
        query=q,
        doc_type=doc_type,
        issuing_authority=issuing_authority,
        year=year,
        effectiveness_status=effectiveness_status,
        limit=200,
    )

    # ── Vector Search ──
    vector_results = _vector_search_by_doc(
        query=q,
        doc_type=doc_type,
        effectiveness_status=effectiveness_status,
        limit=200,
    )

    # ── RRF Fusion ──
    rrf_scores: Dict[int, float] = {}
    doc_data: Dict[int, Dict] = {}
    chunk_previews: Dict[int, str] = {}

    # BM25 contributions
    for result in bm25_results:
        doc_id = result["doc_id"]
        rrf_scores[doc_id] = rrf_scores.get(doc_id, 0) + w_bm25 * _rrf_score(result["rank"])
        doc_data[doc_id] = result["document"]

    # Vector contributions
    for result in vector_results:
        doc_id = result["doc_id"]
        rrf_scores[doc_id] = rrf_scores.get(doc_id, 0) + w_vector * _rrf_score(result["rank"])
        chunk_previews[doc_id] = result.get("top_chunk", "")
        # Nếu doc_data chưa có (chỉ tìm thấy qua vector), fetch từ DB
        if doc_id not in doc_data:
            with get_db() as conn:
                row = conn.execute("SELECT * FROM documents WHERE id = ?", (doc_id,)).fetchone()
                if row:
                    doc_data[doc_id] = dict(row)

    # Fetch all doc type hierarchy ranks
    hierarchy_ranks = {}
    try:
        with get_db() as conn:
            rows = conn.execute("SELECT type_code, hierarchy_rank FROM document_types").fetchall()
            hierarchy_ranks = {r["type_code"]: r["hierarchy_rank"] for r in rows}
    except Exception:
        pass

    # ── Effectiveness & Hierarchy & Time Boosting ──
    for doc_id in rrf_scores:
        if doc_id in doc_data:
            status = doc_data[doc_id].get("effectiveness_status", "")
            boost = EFFECTIVENESS_BOOST.get(status, 1.0)
            
            # Hierarchy Rank boost
            doc_type = doc_data[doc_id].get("doc_type", "")
            rank_score = hierarchy_ranks.get(doc_type, 6)  # mặc định rank trung bình là 6
            hierarchy_boost = 1.0 + (rank_score / 15.0)

            # Time boost (Ưu tiên văn bản mới hơn)
            time_boost = 1.0
            issuing_date = doc_data[doc_id].get("issuing_date", "")
            if issuing_date and len(issuing_date) >= 4:
                try:
                    # Trích xuất năm phát hành (định dạng DD/MM/YYYY hoặc YYYY-MM-DD)
                    year_val = int(issuing_date.split('/')[-1]) if '/' in issuing_date else int(issuing_date[:4])
                    time_boost = 1.0 + max(0, (year_val - 2000) / 100.0)
                except Exception:
                    pass

            rrf_scores[doc_id] *= boost * hierarchy_boost * time_boost

    # Sort
    sorted_doc_ids = sorted(rrf_scores.keys(), key=lambda d: rrf_scores[d], reverse=True)
    total = len(sorted_doc_ids)

    # Paginate
    page_doc_ids = sorted_doc_ids[offset:offset + page_size]

    # Build results
    results = []
    for doc_id in page_doc_ids:
        doc = doc_data.get(doc_id, {})
        # Highlight from BM25 content or vector chunk preview
        highlight_source = doc.get("content_markdown", "") or doc.get("summary", "")
        if not highlight_source and doc_id in chunk_previews:
            highlight_source = chunk_previews[doc_id]

        highlight_text = _highlight(highlight_source, q)

        # Determine search sources
        sources = []
        if any(r["doc_id"] == doc_id for r in bm25_results):
            sources.append("BM25")
        if any(r["doc_id"] == doc_id for r in vector_results):
            sources.append("Vector")

        results.append({
            "document": doc,
            "highlight": highlight_text,
            "score": rrf_scores[doc_id],
            "search_sources": sources,
            "search_mode": mode,
        })

    # Facets
    with get_db() as conn:
        facets = _get_facets(conn, q, "", [])

    return {
        "query": q,
        "total": total,
        "page": page,
        "page_size": page_size,
        "results": results,
        "facets": facets,
        "search_mode": mode,
        "weights": weights,
        "vector_available": len(vector_results) > 0,
    }


def get_similar_documents(doc_id: int, top_k: int = 5) -> List[Dict]:
    """Tìm văn bản tương tự dựa trên vector similarity."""
    with get_db() as conn:
        doc = conn.execute("SELECT * FROM documents WHERE id = ?", (doc_id,)).fetchone()
        if not doc:
            return []
        doc = dict(doc)

    # Tạo query từ title + summary
    query_text = f"{doc.get('title', '')} {doc.get('summary', '')}"
    if not query_text.strip():
        return []

    try:
        from src.core.embedding_service import vector_search as qdrant_search
        results = qdrant_search(query=query_text, top_k=top_k * 3)

        # Nhóm theo doc, loại bỏ chính nó
        seen = set()
        similar = []
        for r in results:
            d_id = r["payload"]["document_id"]
            if d_id != doc_id and d_id not in seen:
                seen.add(d_id)
                with get_db() as conn:
                    row = conn.execute("SELECT * FROM documents WHERE id = ?", (d_id,)).fetchone()
                    if row:
                        similar.append({
                            "document": dict(row),
                            "similarity": r["score"],
                        })
                if len(similar) >= top_k:
                    break
        return similar
    except Exception as e:
        logger.warning(f"[Similar] Error: {e}")
        return []
