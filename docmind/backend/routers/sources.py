import os
import json
import httpx
import base64
import uuid
from fastapi import APIRouter, HTTPException
from typing import List, Dict, Tuple
from models.source import Source, SourceCreate, SourceUpdate, URLSourceCreate, SourceMeta
from models.chunk import Chunk
from services import ingestor, chunker
from services.legal_processor import process_large_document, extract_document_info
from services.crawler import crawl_and_collect_pdfs
from pydantic import BaseModel

router = APIRouter(prefix="/sources")
DATA_DIR = os.getenv("DATA_DIR", "./data")
SOURCES_FILE = os.path.join(DATA_DIR, "sources.json")


# ---------------------------------------------------------------------------
# File I/O helpers
# ---------------------------------------------------------------------------

def load_sources() -> List[Source]:
    if not os.path.exists(SOURCES_FILE):
        return []
    with open(SOURCES_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
        return [Source(**s) for s in data.get("sources", [])]


def save_sources(sources: List[Source]):
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(SOURCES_FILE, "w", encoding="utf-8") as f:
        json.dump(
            {"sources": [s.dict() for s in sources]},
            f, default=str, indent=2, ensure_ascii=False,
        )


def save_chunks(source_id: str, chunks: List[Chunk]):
    chunks_dir = os.path.join(DATA_DIR, "chunks")
    os.makedirs(chunks_dir, exist_ok=True)
    with open(os.path.join(chunks_dir, f"{source_id}.json"), "w", encoding="utf-8") as f:
        json.dump(
            {"source_id": source_id, "chunks": [c.dict() for c in chunks]},
            f, indent=2, ensure_ascii=False,
        )


def save_original_file(source_id: str, content: bytes, extension: str) -> str:
    files_dir = os.path.join(DATA_DIR, "files")
    os.makedirs(files_dir, exist_ok=True)
    filename = f"{source_id}.{extension}"
    with open(os.path.join(files_dir, filename), "wb") as f:
        f.write(content)
    return os.path.join("data", "files", filename)


# ---------------------------------------------------------------------------
# Ingestion pipeline
# ---------------------------------------------------------------------------

_LEGAL_KEYWORDS = [
    "điều", "khoản", "nghị định", "quyết định", "thông tư",
    "chương", "luật", "căn cứ", "chính phủ", "quốc hội",
]


def _is_legal_document(text: str) -> bool:
    text_lower = text.lower()
    return any(kw in text_lower for kw in _LEGAL_KEYWORDS)


def _build_chunks_from_legal(
    legal_chunks: list,
    source_id: str,
    doc_info: dict,
) -> List[Chunk]:
    """Map legal_processor output → Chunk model list."""
    chunks = []
    for i, lc in enumerate(legal_chunks):
        content = lc["content"]
        meta = lc.get("metadata", {})
        chunks.append(Chunk(
            id=f"{source_id}_{i}",
            source_id=source_id,
            index=i,
            text=content,
            token_count=len(content.split()),
            chuong=meta.get("chuong"),
            dieu=meta.get("dieu"),
            khoan=meta.get("khoan"),
            page=meta.get("page"),
            document_number=doc_info.get("document_number"),
            issuance_date=doc_info.get("issuance_date"),
            issuing_authority=doc_info.get("issuing_authority"),
        ))
    return chunks


async def process_pdf(
    b64_content: str,
    source_id: str,
) -> Tuple[List[Chunk], dict, str]:
    """
    Full PDF pipeline — OCR/extract ONCE, then:
      1. Extract doc-level metadata from raw text (header still intact)
      2. Chunk via Legal Processor or simple chunker

    Returns: (chunks, doc_info, joined_text)
    """
    # ── Step 1: Extract text ONCE ─────────────────────────────────────────────
    raw_text, was_ocr = await ingestor.ingest_pdf_smart(b64_content)

    # ── Step 2: Extract document metadata from raw text BEFORE any stripping ──
    if raw_text and len(raw_text.strip()) > 30:
        doc_info = await extract_document_info(raw_text)
        print(f"[Pipeline] doc_info: {doc_info}")
    else:
        doc_info = {"document_number": None, "issuance_date": None, "issuing_authority": None}

    # ── Step 3: Guard — too little text ──────────────────────────────────────
    if not raw_text or len(raw_text.strip()) < 30:
        print(f"[Pipeline] WARNING: Very little text ({len(raw_text.strip())} chars)")
        chunks = [Chunk(
            id=f"{source_id}_0",
            source_id=source_id,
            index=0,
            text=raw_text.strip() or "[Không thể trích xuất nội dung từ file PDF này]",
            token_count=len(raw_text.split()),
            document_number=doc_info.get("document_number"),
            issuance_date=doc_info.get("issuance_date"),
            issuing_authority=doc_info.get("issuing_authority"),
        )]
        return chunks, doc_info, raw_text

    # ── Step 4: Route to Legal Processor or simple chunker ───────────────────
    if _is_legal_document(raw_text) or was_ocr:
        print(f"[Pipeline] Legal Processor (legal={_is_legal_document(raw_text)}, ocr={was_ocr})")
        try:
            legal_chunks = await process_large_document(raw_text)
            chunks = _build_chunks_from_legal(legal_chunks, source_id, doc_info)
            print(f"[Pipeline] Legal Processor → {len(chunks)} structured chunks")
            joined_text = " ".join(c.text for c in chunks)
            return chunks, doc_info, joined_text
        except Exception as e:
            print(f"[Pipeline] Legal Processor failed, falling back: {e}")

    # ── Fallback: simple chunker ──────────────────────────────────────────────
    print("[Pipeline] Using simple chunker")
    chunks = chunker.chunk_text(raw_text, source_id)
    for c in chunks:
        c.document_number = doc_info.get("document_number")
        c.issuance_date = doc_info.get("issuance_date")
        c.issuing_authority = doc_info.get("issuing_authority")
    joined_text = " ".join(c.text for c in chunks)
    return chunks, doc_info, joined_text


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.get("", response_model=Dict[str, List[Source]])
async def get_sources():
    return {"sources": load_sources()}


@router.post("", response_model=Source)
async def create_source(req: SourceCreate):
    source_id = str(uuid.uuid4())

    try:
        if req.type == "pdf":
            binary_content = base64.b64decode(req.content)
            local_path = save_original_file(source_id, binary_content, "pdf")

            chunks, doc_info, text = await process_pdf(req.content, source_id)

        else:
            text = ingestor.get_text_from_source(req.type, req.content)
            local_path = save_original_file(source_id, text.encode("utf-8"), "txt")
            doc_info = {"document_number": None, "issuance_date": None, "issuing_authority": None}
            chunks = chunker.chunk_text(text, source_id)

        save_chunks(source_id, chunks)

        source = Source(
            id=source_id,
            name=req.name,
            type=req.type,
            chunk_count=len(chunks),
            word_count=len(text.split()),
            meta=SourceMeta(
                local_path=local_path,
                document_number=doc_info.get("document_number"),
                issuance_date=doc_info.get("issuance_date"),
                issuing_authority=doc_info.get("issuing_authority"),
            ),
        )

        sources = load_sources()
        sources.append(source)
        save_sources(sources)
        return source

    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/url", response_model=Source)
async def create_source_from_url(req: URLSourceCreate):
    source_id = str(uuid.uuid4())
    print(f"[URL Import] Starting import for {req.url}")

    try:
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            )
        }
        async with httpx.AsyncClient(
            timeout=60.0, headers=headers, follow_redirects=True
        ) as client:
            response = await client.get(req.url)
            if response.status_code != 200:
                raise HTTPException(
                    status_code=400,
                    detail=f"Download failed: HTTP {response.status_code}",
                )

            content_type = response.headers.get("content-type", "").lower()
            binary_content = response.content
            print(f"[URL Import] Downloaded {len(binary_content)} bytes, type={content_type}")

            if "pdf" in content_type or req.url.lower().endswith(".pdf"):
                doc_type = "pdf"
                local_path = save_original_file(source_id, binary_content, "pdf")
                b64_content = base64.b64encode(binary_content).decode("utf-8")

                chunks, doc_info, text = await process_pdf(b64_content, source_id)

            else:
                doc_type = "text"
                local_path = save_original_file(source_id, binary_content, "txt")
                text = binary_content.decode("utf-8", errors="ignore")
                doc_info = {"document_number": None, "issuance_date": None, "issuing_authority": None}
                chunks = chunker.chunk_text(text, source_id)

        save_chunks(source_id, chunks)

        source = Source(
            id=source_id,
            name=req.name or req.url.split("/")[-1] or "Untitled URL",
            type=doc_type,
            chunk_count=len(chunks),
            word_count=len(text.split()),
            meta=SourceMeta(
                url=req.url,
                local_path=local_path,
                document_number=doc_info.get("document_number"),
                issuance_date=doc_info.get("issuance_date"),
                issuing_authority=doc_info.get("issuing_authority"),
            ),
        )

        sources = load_sources()
        sources.append(source)
        save_sources(sources)
        print(f"[URL Import] SUCCESS: {source_id} — {len(chunks)} chunks, {len(text.split())} words")
        return source

    except HTTPException:
        raise
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@router.patch("/{source_id}", response_model=Source)
async def update_source(source_id: str, req: SourceUpdate):
    sources = load_sources()
    source = next((s for s in sources if s.id == source_id), None)
    if not source:
        raise HTTPException(status_code=404, detail="Source not found")

    if req.active is not None:
        source.active = req.active
    if req.name is not None:
        source.name = req.name

    save_sources(sources)
    return source


@router.delete("/{source_id}")
async def delete_source(source_id: str):
    sources = [s for s in load_sources() if s.id != source_id]
    save_sources(sources)

    chunks_path = os.path.join(DATA_DIR, "chunks", f"{source_id}.json")
    if os.path.exists(chunks_path):
        os.remove(chunks_path)

    return {"deleted": True}


# ---------------------------------------------------------------------------
# Crawl endpoint — Auto-scrape government document portals
# ---------------------------------------------------------------------------

class CrawlRequest(BaseModel):
    url: str  # e.g., https://vanban.chinhphu.vn/?pageid=41852&mode=0
    max_documents: int = 10  # Limit to avoid overloading


@router.post("/crawl")
async def crawl_documents(req: CrawlRequest):
    """
    Crawl a government document listing page,
    extract PDF links, download and process each document.
    Returns a summary of results.
    """
    print(f"[Crawl] Starting crawl: {req.url} (max={req.max_documents})")
    
    try:
        # Step 1: Crawl the listing page
        crawled_docs = await crawl_and_collect_pdfs(
            url=req.url,
            max_documents=req.max_documents,
        )
        
        if not crawled_docs:
            return {
                "success": False,
                "message": "Không tìm thấy tài liệu PDF nào trên trang này.",
                "processed": 0,
                "results": []
            }
        
        results = []
        existing_sources = load_sources()
        existing_urls = {s.meta.url for s in existing_sources if s.meta and s.meta.url}
        
        for doc in crawled_docs:
            # Skip if already imported
            if doc.pdf_url in existing_urls:
                results.append({
                    "document_number": doc.document_number,
                    "status": "skipped",
                    "reason": "Đã tồn tại trong hệ thống"
                })
                continue
            
            try:
                # Step 2: Download PDF
                async with httpx.AsyncClient(
                    timeout=60.0,
                    headers={"User-Agent": "Mozilla/5.0"},
                    follow_redirects=True
                ) as client:
                    resp = await client.get(doc.pdf_url)
                    if resp.status_code != 200:
                        results.append({
                            "document_number": doc.document_number,
                            "status": "error",
                            "reason": f"Download failed: HTTP {resp.status_code}"
                        })
                        continue
                    binary_content = resp.content
                
                source_id = str(uuid.uuid4())
                local_path = save_original_file(source_id, binary_content, "pdf")
                b64_content = base64.b64encode(binary_content).decode("utf-8")
                
                # Step 3: Process PDF through pipeline
                chunks, doc_info, text = await process_pdf(b64_content, source_id)
                save_chunks(source_id, chunks)
                
                # Use crawled metadata as fallback if AI extraction failed
                final_doc_number = doc_info.get("document_number") or doc.document_number
                final_date = doc_info.get("issuance_date") or doc.issue_date
                final_authority = doc_info.get("issuing_authority")
                
                source = Source(
                    id=source_id,
                    name=doc.title or final_doc_number,
                    type="pdf",
                    chunk_count=len(chunks),
                    word_count=len(text.split()),
                    meta=SourceMeta(
                        url=doc.pdf_url,
                        local_path=local_path,
                        document_number=final_doc_number,
                        issuance_date=final_date,
                        issuing_authority=final_authority,
                    ),
                )
                
                existing_sources.append(source)
                save_sources(existing_sources)
                
                results.append({
                    "document_number": final_doc_number,
                    "status": "success",
                    "chunks": len(chunks),
                    "source_id": source_id,
                })
                print(f"[Crawl] ✓ {final_doc_number} — {len(chunks)} chunks")
                
            except Exception as e:
                results.append({
                    "document_number": doc.document_number,
                    "status": "error",
                    "reason": str(e)
                })
                print(f"[Crawl] ✗ {doc.document_number}: {e}")
        
        success_count = sum(1 for r in results if r["status"] == "success")
        return {
            "success": True,
            "message": f"Đã xử lý {success_count}/{len(results)} tài liệu thành công.",
            "processed": success_count,
            "results": results
        }
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))