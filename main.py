"""
main.py — FastAPI app cho Phase 1 MVP
Hệ thống Tìm kiếm Văn bản Hành chính Quốc gia
"""

import os
import shutil
from fastapi import FastAPI, Request, Query
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from typing import Optional

from database import init_db
from ingestion import seed_if_empty
from search import search_documents, get_document_detail, list_documents
from models import DOC_TYPE_LABELS, EFFECTIVENESS_LABELS, EFFECTIVENESS_COLORS

# ─── Khởi tạo ──────────────────────────────────────────────────────────────

BASE_DIR = os.path.dirname(__file__)

app = FastAPI(
    title="Hệ thống Tìm kiếm Văn bản Hành chính",
    description="Phase 1 MVP — Full-text search văn bản pháp luật Việt Nam",
    version="1.0.0",
)

app.mount("/static", StaticFiles(directory=os.path.join(BASE_DIR, "static")), name="static")
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))

# Thêm filters cho Jinja2
templates.env.filters["doc_type_label"] = lambda v: DOC_TYPE_LABELS.get(v, v)
templates.env.filters["effectiveness_label"] = lambda v: EFFECTIVENESS_LABELS.get(v, v)
templates.env.filters["effectiveness_color"] = lambda v: EFFECTIVENESS_COLORS.get(v, "status-active")


@app.on_event("startup")
async def startup():
    """Khởi tạo DB và seed dữ liệu mẫu khi server bắt đầu."""
    init_db()
    # Copy file JSON mẫu vào thư mục data/ nếu chưa có
    src = os.path.join(BASE_DIR, "..", "a5d756a6-16d2-4706-b578-d5d50688837c.json")
    dst_dir = os.path.join(BASE_DIR, "data")
    dst = os.path.join(dst_dir, "a5d756a6-16d2-4706-b578-d5d50688837c.json")
    os.makedirs(dst_dir, exist_ok=True)
    if os.path.exists(src) and not os.path.exists(dst):
        shutil.copy2(src, dst)
        print(f"[Startup] Đã copy file JSON mẫu vào data/")
    seed_if_empty()


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
):
    """Trang kết quả tìm kiếm."""
    result = search_documents(
        query=q,
        doc_type=doc_type,
        issuing_authority=authority,
        year=year,
        effectiveness_status=status,
        page=page,
        page_size=10,
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
    })


@app.get("/documents/{doc_id}", response_class=HTMLResponse)
async def document_detail(request: Request, doc_id: int):
    """Trang xem chi tiết 1 văn bản."""
    detail = get_document_detail(doc_id)
    if not detail:
        return HTMLResponse("<h1>404 — Không tìm thấy văn bản</h1>", status_code=404)

    return templates.TemplateResponse("document.html", {
        "request": request,
        "doc": detail["document"],
        "chunks": detail["chunks"],
        "sections": detail["sections"],
        "doc_type_labels": DOC_TYPE_LABELS,
        "effectiveness_labels": EFFECTIVENESS_LABELS,
        "effectiveness_colors": EFFECTIVENESS_COLORS,
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
):
    """REST API: Tìm kiếm văn bản — trả về JSON."""
    result = search_documents(
        query=q,
        doc_type=doc_type,
        issuing_authority=authority,
        year=year,
        effectiveness_status=status,
        page=page,
        page_size=page_size,
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


@app.post("/api/ingest")
async def api_ingest():
    """REST API: Trigger nạp lại dữ liệu từ thư mục data/."""
    from ingestion import ingest_all
    ingest_all()
    return {"message": "Đã nạp dữ liệu xong."}


# ─── Entry point ────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
