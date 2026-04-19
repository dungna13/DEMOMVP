import os
import json
import httpx
import base64
import uuid
from fastapi import APIRouter, HTTPException, BackgroundTasks
from typing import List, Dict
from models.source import Source, SourceCreate, SourceUpdate, URLSourceCreate, SourceMeta
from models.chunk import Chunk
from services import ingestor, chunker
from services.legal_processor import process_large_document

router = APIRouter(prefix="/sources")
DATA_DIR = os.getenv("DATA_DIR", "./data")
SOURCES_FILE = os.path.join(DATA_DIR, "sources.json")

def load_sources() -> List[Source]:
    if not os.path.exists(SOURCES_FILE):
        return []
    with open(SOURCES_FILE, 'r', encoding='utf-8') as f:
        data = json.load(f)
        return [Source(**s) for s in data.get("sources", [])]

def save_sources(sources: List[Source]):
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(SOURCES_FILE, 'w', encoding='utf-8') as f:
        json.dump({"sources": [s.dict() for s in sources]}, f, default=str, indent=2, ensure_ascii=False)

def save_chunks(source_id: str, chunks: List[Chunk]):
    """Save chunks to disk."""
    chunks_dir = os.path.join(DATA_DIR, "chunks")
    os.makedirs(chunks_dir, exist_ok=True)
    with open(os.path.join(chunks_dir, f"{source_id}.json"), 'w', encoding='utf-8') as f:
        json.dump(
            {"source_id": source_id, "chunks": [c.dict() for c in chunks]},
            f, indent=2, ensure_ascii=False
        )

def save_original_file(source_id: str, content: bytes, extension: str) -> str:
    """Save original binary file to storage."""
    files_dir = os.path.join(DATA_DIR, "files")
    os.makedirs(files_dir, exist_ok=True)
    filename = f"{source_id}.{extension}"
    file_path = os.path.join(files_dir, filename)
    with open(file_path, 'wb') as f:
        f.write(content)
    # Return relative path for portability
    return os.path.join("data", "files", filename)


async def smart_ingest_pdf(b64_content: str, source_id: str) -> List[Chunk]:
    """
    Smart PDF ingestion pipeline:
    1. Detect if PDF is scanned or text-based
    2. If scanned: OCR with Gemini Vision -> Legal Processor -> structured chunks
    3. If text-based: extract text -> Legal Processor (if Vietnamese legal doc) or simple chunker
    """
    text, was_ocr = await ingestor.ingest_pdf_smart(b64_content)
    
    if not text or len(text.strip()) < 30:
        print(f"[Pipeline] WARNING: Very little text extracted ({len(text.strip())} chars)")
        return [Chunk(
            id=f"{source_id}_0",
            source_id=source_id,
            index=0,
            text=text.strip() or "[Không thể trích xuất nội dung từ file PDF này]",
            token_count=len(text.split())
        )]
    
    # Detect Vietnamese legal documents by checking for keywords
    legal_keywords = ["điều", "khoản", "nghị định", "quyết định", "thông tư", 
                      "chương", "luật", "căn cứ", "chính phủ", "quốc hội",
                      "Dieu", "Khoan", "Nghi dinh", "Quyet dinh"]
    text_lower = text.lower()
    is_legal = any(kw.lower() in text_lower for kw in legal_keywords)
    
    if is_legal or was_ocr:
        print(f"[Pipeline] Using Legal Processor (legal={is_legal}, ocr={was_ocr})")
        try:
            legal_chunks = await process_large_document(text)
            chunks = []
            for i, lc in enumerate(legal_chunks):
                chunks.append(Chunk(
                    id=f"{source_id}_{i}",
                    source_id=source_id,
                    index=i,
                    text=lc["content"],
                    token_count=len(lc["content"].split()),
                    dieu=lc["metadata"].get("dieu"),
                    khoan=lc["metadata"].get("khoan"),
                    chuong=lc["metadata"].get("chuong"),
                ))
            print(f"[Pipeline] Legal Processor created {len(chunks)} structured chunks")
            return chunks
        except Exception as e:
            print(f"[Pipeline] Legal Processor failed, falling back to simple chunker: {e}")
    
    # Fallback: simple chunker
    print(f"[Pipeline] Using simple chunker")
    return chunker.chunk_text(text, source_id)


@router.get("", response_model=Dict[str, List[Source]])
async def get_sources():
    sources = load_sources()
    return {"sources": sources}

@router.post("", response_model=Source)
async def create_source(req: SourceCreate):
    source_id = str(uuid.uuid4())
    local_path = None
    
    try:
        if req.type == "pdf":
            # 1. Save original file
            binary_content = base64.b64decode(req.content)
            local_path = save_original_file(source_id, binary_content, "pdf")
            
            # 2. Process with smart pipeline
            chunks = await smart_ingest_pdf(req.content, source_id)
            text = " ".join([c.text for c in chunks])
        else:
            # 1. Save original text file
            text = ingestor.get_text_from_source(req.type, req.content)
            local_path = save_original_file(source_id, text.encode('utf-8'), "txt")
            
            # 2. Simple chunking
            chunks = chunker.chunk_text(text, source_id)
        
        save_chunks(source_id, chunks)
            
        source = Source(
            id=source_id,
            name=req.name,
            type=req.type,
            chunk_count=len(chunks),
            word_count=len(text.split()),
            meta=SourceMeta(local_path=local_path)
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
        # 1. Download content
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }
        async with httpx.AsyncClient(timeout=60.0, headers=headers, follow_redirects=True) as client:
            response = await client.get(req.url)
            if response.status_code != 200:
                raise HTTPException(status_code=400, detail=f"Download failed: HTTP {response.status_code}")
            
            content_type = response.headers.get("content-type", "").lower()
            binary_content = response.content
            print(f"[URL Import] Downloaded {len(binary_content)} bytes. Type: {content_type}")
            
            # 2. Determine type and process
            if "pdf" in content_type or req.url.lower().endswith(".pdf"):
                doc_type = "pdf"
                local_path = save_original_file(source_id, binary_content, "pdf")
                b64_content = base64.b64encode(binary_content).decode('utf-8')
                chunks = await smart_ingest_pdf(b64_content, source_id)
                text = " ".join([c.text for c in chunks])
            else:
                doc_type = "text"
                local_path = save_original_file(source_id, binary_content, "txt")
                text = binary_content.decode('utf-8', errors='ignore')
                chunks = chunker.chunk_text(text, source_id)
            
            # 3. Save chunks
            save_chunks(source_id, chunks)
                
            # 4. Create and save source record
            source = Source(
                id=source_id,
                name=req.name or req.url.split("/")[-1] or "Untitled URL",
                type=doc_type,
                chunk_count=len(chunks),
                word_count=len(text.split()),
                meta=SourceMeta(url=req.url, local_path=local_path)
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
    sources = load_sources()
    sources = [s for s in sources if s.id != source_id]
    save_sources(sources)
    
    # Delete chunks file
    chunks_path = os.path.join(DATA_DIR, "chunks", f"{source_id}.json")
    if os.path.exists(chunks_path):
        os.remove(chunks_path)
        
    return {"deleted": True}
