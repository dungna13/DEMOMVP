"""
main.py — FastAPI app cho Phase 1 + Phase 2 + Phase 3
Hệ thống Tìm kiếm Văn bản Hành chính Quốc gia
Phase 3: Knowledge Wiki (Karpathy LLM Wiki Pattern)
"""

import os
import sys
import json
import shutil
import logging

# Fix Windows console encoding for Vietnamese text
os.environ.setdefault("PYTHONUTF8", "1")
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from fastapi import FastAPI, Request, Query, Body, Response
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from typing import Optional

from src.database.database import init_db, get_db
from src.services.ingestion import seed_if_empty
from src.services.search import search_documents, get_document_detail, list_documents
from src.database.models import (
    DOC_TYPE_LABELS, EFFECTIVENESS_LABELS, EFFECTIVENESS_COLORS,
    RELATION_TYPE_LABELS, RELATION_TYPE_ICONS,
)
from src.services.wiki_compiler import (
    compile_all_wiki, compile_wiki_for_document, lint_wiki, get_wiki_status
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Khởi tạo DB và chạy các tác vụ nặng ở chế độ ngầm."""
    init_db()
    seed_if_empty()

    # Chạy Reindex và Extract Relations trong background
    async def background_startup_tasks():
        global _vector_indexed
        
        # 1. Build vector index
        try:
            from src.core.embedding_service import reindex_all_chunks
            count = await asyncio.to_thread(reindex_all_chunks)
            _vector_indexed = count > 0
            logger.info(f"[Background] Vector index built: {count} chunks")
        except Exception as e:
            logger.warning(f"[Background] Vector index skipped: {e}")

        # 2. Extract legal relations
        try:
            from src.services.legal_relations import extract_all_relations
            rel_count = await asyncio.to_thread(extract_all_relations)
            logger.info(f"[Background] Extracted {rel_count} legal relations")
        except Exception as e:
            logger.warning(f"[Background] Relations extraction skipped: {e}")

    # Tạo task chạy ngầm
    asyncio.create_task(background_startup_tasks())
    logger.info("🚀 Server is starting... App will be available at http://localhost:8000 while AI is processing in background.")
    yield

# ─── Khởi tạo ──────────────────────────────────────────────────────────────

BASE_DIR = os.path.dirname(__file__)

app = FastAPI(
    title="Hệ thống Tìm kiếm Văn bản Hành chính",
    description="Phase 2 — Hybrid Search + RAG Q&A + Legal Relations",
    version="2.0.0",
    lifespan=lifespan,
)

app.mount("/static", StaticFiles(directory=os.path.join(BASE_DIR, "static")), name="static")
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))

# Thêm filters cho Jinja2
templates.env.filters["doc_type_label"] = lambda v: DOC_TYPE_LABELS.get(v, v)
templates.env.filters["effectiveness_label"] = lambda v: EFFECTIVENESS_LABELS.get(v, v)
templates.env.filters["effectiveness_color"] = lambda v: EFFECTIVENESS_COLORS.get(v, "status-active")
templates.env.filters["relation_label"] = lambda v: RELATION_TYPE_LABELS.get(v, v)
templates.env.filters["relation_icon"] = lambda v: RELATION_TYPE_ICONS.get(v, "📄")

# Track vector index state
_vector_indexed = False

import asyncio


@app.get("/favicon.ico", include_in_schema=False)
async def favicon():
    return Response(status_code=204)


# ─── HTML Routes ───────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    """Trang chủ — search portal."""
    return templates.TemplateResponse("index.html", {
        "request": request,
        "query": "",
        "results": [],
        "total": 0,
        "facets": {},
        "filters": {},
        "doc_type_labels": DOC_TYPE_LABELS,
        "effectiveness_labels": EFFECTIVENESS_LABELS,
        "page": 1,
        "page_size": 10,
        "search_mode": "balanced",
        "vector_available": _vector_indexed,
    })


@app.get("/search", response_class=HTMLResponse)
async def search_page(
    request: Request,
    q: str = Query(default="", alias="q"),
    doc_type: Optional[str] = None,
    authority: Optional[str] = None,
    year: Optional[int] = None,
    status: Optional[str] = None,
    page: int = 1,
    mode: Optional[str] = None,
):
    """Trang kết quả tìm kiếm — sử dụng Hybrid Search nếu có vector index."""
    if _vector_indexed and q:
        # Phase 2: Hybrid Search (BM25 + Vector + RRF)
        try:
            from src.core.vector_search import hybrid_search
            result = hybrid_search(
                query=q,
                doc_type=doc_type,
                issuing_authority=authority,
                year=year,
                effectiveness_status=status,
                page=page,
                page_size=10,
                search_mode=mode,
            )
        except Exception as e:
            logger.warning(f"[Search] Hybrid search failed, falling back to BM25: {e}")
            result = search_documents(
                query=q, doc_type=doc_type, issuing_authority=authority,
                year=year, effectiveness_status=status, page=page, page_size=10,
            )
    else:
        # Phase 1: BM25 only
        result = search_documents(
            query=q, doc_type=doc_type, issuing_authority=authority,
            year=year, effectiveness_status=status, page=page, page_size=10,
        )

    return templates.TemplateResponse("index.html", {
        "request": request,
        "query": q,
        "results": result["results"],
        "total": result["total"],
        "facets": result["facets"],
        "filters": {
            "doc_type": doc_type,
            "authority": authority,
            "year": year,
            "status": status,
        },
        "doc_type_labels": DOC_TYPE_LABELS,
        "effectiveness_labels": EFFECTIVENESS_LABELS,
        "page": page,
        "page_size": 10,
        "search_mode": result.get("search_mode", "balanced"),
        "vector_available": result.get("vector_available", _vector_indexed),
    })


@app.get("/documents/{doc_id}", response_class=HTMLResponse)
async def document_detail(request: Request, doc_id: int):
    """Trang xem chi tiết 1 văn bản + quan hệ pháp lý."""
    detail = get_document_detail(doc_id)
    if not detail:
        return HTMLResponse("<h1>404 — Không tìm thấy văn bản</h1>", status_code=404)

    # Phase 2: Lấy quan hệ pháp lý
    relations = {"outgoing": [], "incoming": [], "relation_labels": RELATION_TYPE_LABELS}
    try:
        from src.services.legal_relations import get_document_relations
        relations = get_document_relations(doc_id)
    except Exception as e:
        logger.warning(f"[Detail] Relations failed: {e}")

    # Phase 2: Lấy văn bản tương tự
    similar = []
    try:
        from src.core.vector_search import get_similar_documents
        similar = get_similar_documents(doc_id, top_k=5)
    except Exception:
        pass

    # Phase 2: Lấy legal fields
    legal_fields = []
    try:
        from database import get_db
        with get_db() as conn:
            fields = conn.execute(
                "SELECT * FROM doc_legal_fields WHERE document_id = ?", (doc_id,)
            ).fetchall()
            legal_fields = [dict(f) for f in fields]
    except Exception:
        pass

    return templates.TemplateResponse("document.html", {
        "request": request,
        "doc": detail["document"],
        "chunks": detail["chunks"],
        "sections": detail["sections"],
        "doc_type_labels": DOC_TYPE_LABELS,
        "effectiveness_labels": EFFECTIVENESS_LABELS,
        "effectiveness_colors": EFFECTIVENESS_COLORS,
        "relations": relations,
        "similar_docs": similar,
        "legal_fields": legal_fields,
        "relation_labels": RELATION_TYPE_LABELS,
        "relation_icons": RELATION_TYPE_ICONS,
    })


@app.get("/qa", response_class=HTMLResponse)
async def qa_page(request: Request):
    """Trang hỏi đáp pháp luật (RAG Q&A)."""
    from src.core.rag_engine import get_suggested_questions
    from src.core.ai_service import is_ai_available

    return templates.TemplateResponse("qa.html", {
        "request": request,
        "suggested_questions": get_suggested_questions(),
        "ai_available": is_ai_available(),
    })


# ─── REST API Routes ────────────────────────────────────────────────────────

@app.get("/api/search")
async def api_search(
    q: str = Query(default=""),
    doc_type: Optional[str] = None,
    authority: Optional[str] = None,
    year: Optional[int] = None,
    status: Optional[str] = None,
    page: int = 1,
    page_size: int = 10,
    mode: Optional[str] = None,
):
    """REST API: Tìm kiếm văn bản — Hybrid Search."""
    if _vector_indexed and q:
        try:
            from src.core.vector_search import hybrid_search
            result = hybrid_search(
                query=q, doc_type=doc_type, issuing_authority=authority,
                year=year, effectiveness_status=status,
                page=page, page_size=page_size, search_mode=mode,
            )
            return JSONResponse(content=result)
        except Exception:
            pass

    result = search_documents(
        query=q, doc_type=doc_type, issuing_authority=authority,
        year=year, effectiveness_status=status,
        page=page, page_size=page_size,
    )
    return JSONResponse(content=result)


@app.get("/api/documents")
async def api_list_documents(page: int = 1, page_size: int = 20):
    """REST API: Danh sách toàn bộ văn bản."""
    return JSONResponse(content=list_documents(page=page, page_size=page_size))


@app.get("/api/documents/{doc_id}")
async def api_document_detail(doc_id: int):
    """REST API: Chi tiết 1 văn bản."""
    detail = get_document_detail(doc_id)
    if not detail:
        return JSONResponse({"error": "Không tìm thấy văn bản"}, status_code=404)
    return JSONResponse(content=detail)


@app.get("/api/documents/{doc_id}/relations")
async def api_document_relations(doc_id: int):
    """REST API: Quan hệ pháp lý của 1 văn bản."""
    try:
        from src.services.legal_relations import get_document_relations
        return JSONResponse(content=get_document_relations(doc_id))
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@app.get("/api/documents/{doc_id}/similar")
async def api_similar_documents(doc_id: int, top_k: int = 5):
    """REST API: Văn bản tương tự."""
    try:
        from src.core.vector_search import get_similar_documents
        results = get_similar_documents(doc_id, top_k=top_k)
        return JSONResponse(content={"similar": results})
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@app.post("/api/qa")
async def api_qa(request: Request):
    """REST API: Hỏi đáp pháp luật (RAG)."""
    try:
        body = await request.json()
        question = body.get("question", "")
        chat_history = body.get("chat_history", [])

        if not question.strip():
            return JSONResponse({"error": "Câu hỏi không được để trống"}, status_code=400)

        from src.core.rag_engine import ask_question
        result = ask_question(question=question, chat_history=chat_history)
        return JSONResponse(content=result)
    except Exception as e:
        logger.error(f"[QA] Error: {e}")
        return JSONResponse({"error": str(e)}, status_code=500)


@app.post("/api/ingest")
async def api_ingest():
    """REST API: Trigger nạp lại dữ liệu từ thư mục data/."""
    from src.services.ingestion import ingest_all
    ingest_all()

    # Rebuild vector index
    try:
        from src.core.embedding_service import reindex_all_chunks
        count = reindex_all_chunks()
        global _vector_indexed
        _vector_indexed = count > 0
    except Exception:
        pass

    # Re-extract relations
    try:
        from src.services.legal_relations import extract_all_relations
        extract_all_relations()
    except Exception:
        pass

    return {"message": "Đã nạp dữ liệu xong và cập nhật vector index."}


# ─── Phase 3: Wiki Web Pages ─────────────────────────────────────────────────

@app.get("/wiki", response_class=HTMLResponse)
async def wiki_index(request: Request, field: Optional[str] = None, page: int = 1):
    """Trang danh sách Knowledge Wiki."""
    with get_db() as conn:
        q = "SELECT id, slug, title, doc_number, legal_fields, summary, reviewed, lint_status, created_at FROM wiki_pages"
        params = []
        if field:
            q += " WHERE legal_fields LIKE ?"
            params.append(f'%{field}%')
        q += " ORDER BY created_at DESC LIMIT 50"
        pages_rows = conn.execute(q, params).fetchall()
        total = conn.execute("SELECT COUNT(*) as n FROM wiki_pages").fetchone()["n"]
        status = get_wiki_status()

    wiki_pages_list = []
    for r in pages_rows:
        fields = []
        try:
            fields = json.loads(r["legal_fields"] or "[]")
        except Exception:
            pass
        wiki_pages_list.append({
            "id": r["id"], "slug": r["slug"], "title": r["title"],
            "doc_number": r["doc_number"], "legal_fields": fields,
            "summary": (r["summary"] or "")[:200],
            "reviewed": r["reviewed"], "lint_status": r["lint_status"],
            "created_at": r["created_at"],
        })
    return templates.TemplateResponse("wiki.html", {
        "request": request, "wiki_pages": wiki_pages_list, "total": total,
        "status": status, "field_filter": field,
    })


@app.get("/wiki/{slug}", response_class=HTMLResponse)
async def wiki_page(request: Request, slug: str):
    """Trang xem chi tiết một wiki page."""
    with get_db() as conn:
        page = conn.execute("SELECT * FROM wiki_pages WHERE slug=?", (slug,)).fetchone()
    if not page:
        return HTMLResponse("<h1>404 — Không tìm thấy trang wiki</h1>", status_code=404)

    page = dict(page)
    for field in ("key_points", "suggested_qa", "entities", "legal_fields", "tags"):
        try:
            page[field] = json.loads(page.get(field) or "[]")
        except Exception:
            page[field] = []

    return templates.TemplateResponse("wiki_page.html", {"request": request, "page": page})


# ─── Phase 3: REST API ────────────────────────────────────────────────────────

@app.get("/api/phase3/status")
async def api_phase3_status():
    """REST API: Trạng thái Phase 3 Knowledge Wiki."""
    return JSONResponse(content=get_wiki_status())


@app.post("/api/phase3/compile")
async def api_phase3_compile(
    limit: Optional[int] = Query(None),
    skip_existing: bool = Query(True),
):
    """REST API: Trigger biên dịch Phase 3 (Knowledge Wiki)."""
    try:
        count = await asyncio.to_thread(compile_all_wiki, limit=limit, skip_existing=skip_existing)
        status = get_wiki_status()
        return {"compiled": count, "status": status}
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@app.post("/api/phase3/compile/{doc_id}")
async def api_phase3_compile_doc(doc_id: int):
    """REST API: Biên dịch Phase 3 cho 1 văn bản cụ thể."""
    try:
        path = await asyncio.to_thread(compile_wiki_for_document, doc_id)
        if not path:
            return JSONResponse({"error": "Không tìm thấy văn bản"}, status_code=404)
        return {"message": "Biên dịch thành công", "file": path}
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@app.post("/api/phase3/lint")
async def api_phase3_lint():
    """REST API: Chạy lint wiki."""
    try:
        issues = await asyncio.to_thread(lint_wiki)
        return JSONResponse(content={"issues_count": len(issues), "issues": issues})
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@app.get("/api/wiki")
async def api_wiki_list(field: Optional[str] = None, page: int = 1, page_size: int = 20):
    """REST API: Danh sách wiki pages."""
    with get_db() as conn:
        q = "SELECT slug, title, doc_number, legal_fields, summary, reviewed, lint_status FROM wiki_pages"
        params = []
        if field:
            q += " WHERE legal_fields LIKE ?"
            params.append(f'%{field}%')
        offset = (page - 1) * page_size
        q += f" ORDER BY created_at DESC LIMIT {page_size} OFFSET {offset}"
        rows = conn.execute(q, params).fetchall()
        total = conn.execute("SELECT COUNT(*) as n FROM wiki_pages").fetchone()["n"]
    results = []
    for r in rows:
        try:
            fields = json.loads(r["legal_fields"] or "[]")
        except Exception:
            fields = []
        results.append(dict(slug=r["slug"], title=r["title"], doc_number=r["doc_number"],
                           legal_fields=fields, summary=(r["summary"] or "")[:200],
                           reviewed=bool(r["reviewed"]), lint_status=r["lint_status"]))
    return JSONResponse(content={"total": total, "page": page, "results": results})


@app.get("/api/wiki/{slug}")
async def api_wiki_page(slug: str):
    """REST API: Nội dung chi tiết một wiki page."""
    with get_db() as conn:
        row = conn.execute("SELECT * FROM wiki_pages WHERE slug=?", (slug,)).fetchone()
    if not row:
        return JSONResponse({"error": "Không tìm thấy"}, status_code=404)
    page = dict(row)
    for field in ("key_points", "suggested_qa", "entities", "legal_fields", "tags"):
        try:
            page[field] = json.loads(page.get(field) or "[]")
        except Exception:
            page[field] = []
    return JSONResponse(content=page)


@app.get("/api/vector-info")
async def api_vector_info():
    """REST API: Thông tin vector index."""
    try:
        from src.core.embedding_service import get_collection_info
        return JSONResponse(content=get_collection_info())
    except Exception as e:
        return JSONResponse({"error": str(e), "vector_indexed": _vector_indexed})


@app.get("/api/system-status")
async def api_system_status():
    """REST API: Trạng thái hệ thống."""
    from src.core.ai_service import is_ai_available
    from src.database.database import get_db

    with get_db() as conn:
        doc_count = conn.execute("SELECT COUNT(*) as cnt FROM documents").fetchone()["cnt"]
        chunk_count = conn.execute("SELECT COUNT(*) as cnt FROM chunks").fetchone()["cnt"]
        rel_count = conn.execute("SELECT COUNT(*) as cnt FROM doc_relations").fetchone()["cnt"]

    wiki_count = 0
    try:
        wiki_count = conn.execute("SELECT COUNT(*) as n FROM wiki_pages").fetchone()["n"]
    except Exception:
        pass
    return JSONResponse(content={
        "phase": 3,
        "documents": doc_count,
        "chunks": chunk_count,
        "relations": rel_count,
        "wiki_pages": wiki_count,
        "vector_indexed": _vector_indexed,
        "ai_available": is_ai_available(),
        "search_modes": ["keyword", "semantic", "balanced"],
    })


# ─── Entry point ────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
