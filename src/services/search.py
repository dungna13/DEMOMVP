"""
search.py — Full-text search logic dùng SQLite FTS5 (simulate BM25)
Phase 1: BM25 ranking, snippet highlight, facet counts
"""

import re
from typing import Optional, List, Dict, Any
from src.database.database import get_db


# ========== EFFECTIVENESS BOOST (theo HLD) ==========
EFFECTIVENESS_BOOST = {
    "con_hieu_luc": 2.0,
    "chua_co_hieu_luc": 1.5,
    "het_hieu_luc_mot_phan": 1.0,
    "het_hieu_luc": 0.3,
}


def _highlight(text: str, query: str, max_len: int = 200) -> str:
    """Tạo snippet với highlight từ khóa."""
    if not text:
        return ""

    # Tìm vị trí xuất hiện từ khóa đầu tiên
    words = [w.strip() for w in query.split() if len(w.strip()) >= 2]
    best_pos = 0
    for word in words:
        pos = text.lower().find(word.lower())
        if pos != -1:
            best_pos = max(0, pos - 50)
            break

    snippet = text[best_pos : best_pos + max_len]
    if best_pos > 0:
        snippet = "..." + snippet
    if best_pos + max_len < len(text):
        snippet = snippet + "..."

    # Highlight các từ khóa
    for word in words:
        if len(word) >= 2:
            pattern = re.compile(re.escape(word), re.IGNORECASE)
            snippet = pattern.sub(f'<mark>{word}</mark>', snippet)

    return snippet


def _build_fts_query(query: str) -> str:
    """Chuyển query người dùng sang FTS5 query."""
    # Tách từ, loại ký tự đặc biệt FTS5
    words = re.findall(r'[\w\d/\-]+', query, re.UNICODE)
    if not words:
        return '""'
    # Dùng NEAR cho nhiều từ, hoặc OR nếu chỉ 1 từ
    if len(words) == 1:
        return f'"{words[0]}"*'
    terms = " OR ".join(f'"{w}"*' for w in words)
    return terms


def search_documents(
    query: str,
    doc_type: Optional[str] = None,
    issuing_authority: Optional[str] = None,
    year: Optional[int] = None,
    effectiveness_status: Optional[str] = None,
    page: int = 1,
    page_size: int = 10,
) -> Dict[str, Any]:
    """
    Tìm kiếm văn bản theo HLD Phase 1:
    - FTS5 full-text (BM25 mặc định của SQLite)
    - Filter facet: loại VB, cơ quan, năm, hiệu lực
    - Effectiveness boosting
    """
    offset = (page - 1) * page_size

    with get_db() as conn:
        # ---- Build filter clauses ----
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

        # ---- FTS5 search ----
        q = query.strip()

        if q:
            fts_q = _build_fts_query(q)
            # Tìm document id từ FTS5 → join với documents
            sql = f"""
                SELECT
                    d.*,
                    bm25(documents_fts) AS raw_score
                FROM documents_fts
                JOIN documents d ON documents_fts.rowid = d.id
                WHERE documents_fts MATCH ?
                {filter_sql}
                ORDER BY raw_score
                LIMIT ? OFFSET ?
            """
            rows = conn.execute(sql, [fts_q] + params + [page_size, offset]).fetchall()

            # Count
            count_sql = f"""
                SELECT COUNT(*) as cnt
                FROM documents_fts
                JOIN documents d ON documents_fts.rowid = d.id
                WHERE documents_fts MATCH ?
                {filter_sql}
            """
            total = conn.execute(count_sql, [fts_q] + params).fetchone()["cnt"]

        else:
            # Không có query → trả về tất cả (sắp xếp theo ngày)
            where = ("WHERE " + " AND ".join(filters)) if filters else ""
            sql = f"""
                SELECT d.*, 0 AS raw_score
                FROM documents d
                {where}
                ORDER BY d.issuing_date DESC
                LIMIT ? OFFSET ?
            """
            rows = conn.execute(sql, params + [page_size, offset]).fetchall()
            count_sql = f"SELECT COUNT(*) as cnt FROM documents d {where}"
            total = conn.execute(count_sql, params).fetchone()["cnt"]

        # ---- Build results ----
        results = []
        for row in rows:
            doc = dict(row)
            boost = EFFECTIVENESS_BOOST.get(doc.get("effectiveness_status", ""), 1.0)
            score = abs(float(doc.get("raw_score", 0))) * boost

            # Highlight snippet
            highlight_text = _highlight(
                doc.get("content_markdown", "") or doc.get("summary", ""),
                q or doc.get("title", ""),
            )

            results.append({
                "document": doc,
                "highlight": highlight_text,
                "score": score,
            })

        # Re-sort nếu có query (đã boost effectiveness)
        if q:
            results.sort(key=lambda x: x["score"], reverse=True)

        # ---- Facet counts ----
        facets = _get_facets(conn, q, filter_sql, params)

        return {
            "query": q,
            "total": total,
            "page": page,
            "page_size": page_size,
            "results": results,
            "facets": facets,
        }


def _get_facets(conn, query: str, filter_sql: str, params: List) -> Dict:
    """Tính facet counts cho sidebar filter."""
    # Giảm thiểu complexity: dùng GROUP BY trực tiếp trên documents
    try:
        doc_types = conn.execute(
            "SELECT doc_type, COUNT(*) as cnt FROM documents GROUP BY doc_type"
        ).fetchall()

        authorities = conn.execute(
            "SELECT issuing_authority, COUNT(*) as cnt FROM documents GROUP BY issuing_authority ORDER BY cnt DESC LIMIT 10"
        ).fetchall()

        statuses = conn.execute(
            "SELECT effectiveness_status, COUNT(*) as cnt FROM documents GROUP BY effectiveness_status"
        ).fetchall()

        years_raw = conn.execute(
            "SELECT issuing_date FROM documents WHERE issuing_date IS NOT NULL"
        ).fetchall()

        year_counts: Dict[str, int] = {}
        for r in years_raw:
            date_str = r["issuing_date"] or ""
            # Format DD/MM/YYYY hoặc YYYY-...
            parts = date_str.replace("-", "/").split("/")
            year = None
            for p in parts:
                if len(p) == 4 and p.isdigit():
                    year = p
                    break
            if year:
                year_counts[year] = year_counts.get(year, 0) + 1

        return {
            "doc_types": [dict(r) for r in doc_types],
            "authorities": [dict(r) for r in authorities],
            "effectiveness": [dict(r) for r in statuses],
            "years": [{"year": k, "cnt": v} for k, v in sorted(year_counts.items(), reverse=True)],
        }
    except Exception:
        return {}


def get_document_detail(doc_id: int) -> Optional[Dict]:
    """Lấy chi tiết 1 văn bản gồm chunks và sections."""
    with get_db() as conn:
        doc = conn.execute("SELECT * FROM documents WHERE id = ?", (doc_id,)).fetchone()
        if not doc:
            return None

        chunks = conn.execute(
            "SELECT * FROM chunks WHERE document_id = ? ORDER BY chunk_index",
            (doc_id,),
        ).fetchall()

        sections = conn.execute(
            "SELECT * FROM doc_sections WHERE document_id = ? ORDER BY id",
            (doc_id,),
        ).fetchall()

        return {
            "document": dict(doc),
            "chunks": [dict(c) for c in chunks],
            "sections": [dict(s) for s in sections],
        }


def list_documents(page: int = 1, page_size: int = 20) -> Dict:
    """Liệt kê tất cả văn bản (phân trang)."""
    offset = (page - 1) * page_size
    with get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM documents ORDER BY issuing_date DESC LIMIT ? OFFSET ?",
            (page_size, offset),
        ).fetchall()
        total = conn.execute("SELECT COUNT(*) as cnt FROM documents").fetchone()["cnt"]
        return {
            "total": total,
            "page": page,
            "page_size": page_size,
            "documents": [dict(r) for r in rows],
        }
