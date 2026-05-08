"""
main.py — FastAPI app cho Phase 1 + Phase 2
Hệ thống Tìm kiếm Văn bản Hành chính Quốc gia
Phase 2: Hybrid Search + RAG Q&A + Legal Relations
"""

import os
import shutil
import logging
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

    return JSONResponse(content={
        "phase": 2,
        "documents": doc_count,
        "chunks": chunk_count,
        "relations": rel_count,
        "vector_indexed": _vector_indexed,
        "ai_available": is_ai_available(),
        "search_modes": ["keyword", "semantic", "balanced"],
    })


# ─── Entry point ────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
