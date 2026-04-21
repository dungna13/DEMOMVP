"""
DocMind Full Crawler — Crawl all 1950 pages from vanban.chinhphu.vn
Saves chunks as JSON files compatible with DocMind's RAG pipeline.

Usage:
    python full_crawl.py                  # Run all phases
    python full_crawl.py --phase 1        # Only crawl listings
    python full_crawl.py --phase 2        # Only download PDFs
    python full_crawl.py --phase 3        # Only extract + chunk + save JSON
    python full_crawl.py --status         # Show progress
"""

import asyncio
import sqlite3
import os
import sys
import json
import uuid
import re
import time
import argparse
import hashlib
from datetime import datetime
from typing import List, Dict, Any, Optional, Tuple
from pathlib import Path

import httpx
from bs4 import BeautifulSoup

# --- Try importing PDF libs (only needed for phase 3) ---
try:
    import pymupdf
    fitz = pymupdf
    HAS_PYMUPDF = True
except ImportError:
    HAS_PYMUPDF = False

# ============================================================
# CONFIGURATION
# ============================================================
BASE_URL = "https://vanban.chinhphu.vn/he-thong-van-ban?mode=0"
MAX_PAGES = 1950
CONCURRENT_REQUESTS = 5        # Concurrent HTTP requests
CHUNK_SIZE_PAGES = 50          # Pages per batch (phase 1)
PDF_BATCH_SIZE = 20            # PDFs per batch (phase 2)
TARGET_TOKENS = 400            # Chunk target token count
OVERLAP_SENTENCES = 2          # Sentence overlap between chunks
REQUEST_TIMEOUT = 45.0         # HTTP timeout in seconds

# Paths
DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
DB_PATH = os.path.join(DATA_DIR, "full_crawl_progress.db")
CHUNKS_DIR = os.path.join(DATA_DIR, "chunks")
FILES_DIR = os.path.join(DATA_DIR, "files")
SOURCES_PATH = os.path.join(DATA_DIR, "sources.json")

BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "vi-VN,vi;q=0.9,en;q=0.8",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

# Ensure directories exist
os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(CHUNKS_DIR, exist_ok=True)
os.makedirs(FILES_DIR, exist_ok=True)


# ============================================================
# DATABASE SETUP
# ============================================================
def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db()
    c = conn.cursor()
    c.executescript("""
        CREATE TABLE IF NOT EXISTS pages (
            page_num INTEGER PRIMARY KEY,
            status TEXT DEFAULT 'pending',
            doc_count INTEGER DEFAULT 0,
            updated_at TEXT
        );
        CREATE TABLE IF NOT EXISTS documents (
            id TEXT PRIMARY KEY,
            doc_number TEXT,
            title TEXT,
            issue_date TEXT,
            pdf_url TEXT,
            source_page INTEGER,
            pdf_status TEXT DEFAULT 'pending',
            chunk_status TEXT DEFAULT 'pending',
            pdf_path TEXT,
            created_at TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_doc_pdf_status ON documents(pdf_status);
        CREATE INDEX IF NOT EXISTS idx_doc_chunk_status ON documents(chunk_status);
    """)
    conn.commit()
    conn.close()


# ============================================================
# PHASE 1: CRAWL LISTING PAGES
# ============================================================
def parse_listing_page(html: str, page_num: int) -> List[Dict[str, Any]]:
    """Parse a listing page and extract document metadata."""
    soup = BeautifulSoup(html, "html.parser")
    docs = []
    rows = soup.find_all("tr")

    for row in rows:
        cells = row.find_all("td")
        if len(cells) < 3:
            continue

        # Cell 0: Document number
        doc_number = ""
        number_elem = cells[0].find("a")
        if number_elem:
            span = number_elem.find("span")
            doc_number = (span.get_text(strip=True) if span
                         else number_elem.get_text(strip=True))
        else:
            doc_number = cells[0].get_text(strip=True)

        if not doc_number or doc_number in ("Số ký hiệu", "STT"):
            continue

        # Cell 1: Issue date
        issue_date = cells[1].get_text(strip=True)

        # Cell 2: Title + PDF link
        title = ""
        pdf_url = None
        for link in cells[2].find_all("a"):
            href = link.get("href", "")
            text = link.get_text(strip=True)
            if "datafiles.chinhphu.vn" in href and href.endswith(".pdf"):
                if not href.startswith("http"):
                    href = "https:" + href if href.startswith("//") else href
                pdf_url = href
            elif text and "đính kèm" not in text.lower():
                title = text

        if not title:
            title = cells[2].get_text(strip=True)[:300]

        # Generate stable ID from doc_number + title
        raw_id = f"{doc_number}|{title}"
        doc_id = hashlib.md5(raw_id.encode("utf-8")).hexdigest()[:12]
        doc_id = f"{doc_id}-{uuid.uuid4().hex[:20]}"

        docs.append({
            "id": doc_id,
            "doc_number": doc_number,
            "title": title,
            "issue_date": issue_date,
            "pdf_url": pdf_url,
            "source_page": page_num,
        })

    return docs


async def fetch_page(client: httpx.AsyncClient, page_num: int,
                     semaphore: asyncio.Semaphore) -> Optional[str]:
    async with semaphore:
        url = f"{BASE_URL}&p={page_num}"
        for attempt in range(3):
            try:
                resp = await client.get(url, timeout=REQUEST_TIMEOUT)
                if resp.status_code == 200:
                    return resp.text
                print(f"  [!] Page {page_num}: HTTP {resp.status_code}")
            except Exception as e:
                print(f"  [!] Page {page_num} attempt {attempt+1}: {e}")
                await asyncio.sleep(2 * (attempt + 1))
        return None


async def phase1_crawl_listings(max_pages: int = MAX_PAGES):
    """Phase 1: Crawl all listing pages and save document metadata to DB."""
    print("\n" + "=" * 60)
    print(f"PHASE 1: CRAWLING LISTING PAGES (1-{max_pages})")
    print("=" * 60)

    conn = get_db()
    c = conn.cursor()

    # Find which pages are already done
    c.execute("SELECT page_num FROM pages WHERE status='completed'")
    completed = {row[0] for row in c.fetchall()}
    pages_todo = [p for p in range(1, max_pages + 1) if p not in completed]

    print(f"[Phase 1] {len(completed)} done, {len(pages_todo)} remaining")
    if not pages_todo:
        print("[Phase 1] All pages already crawled!")
        conn.close()
        return

    conn.close()

    semaphore = asyncio.Semaphore(CONCURRENT_REQUESTS)
    total_docs = 0
    start = time.time()

    async with httpx.AsyncClient(headers=BROWSER_HEADERS, follow_redirects=True) as client:
        for i in range(0, len(pages_todo), CHUNK_SIZE_PAGES):
            batch = pages_todo[i:i + CHUNK_SIZE_PAGES]
            tasks = [fetch_page(client, p, semaphore) for p in batch]
            results = await asyncio.gather(*tasks)

            conn = get_db()
            c = conn.cursor()
            batch_docs = 0

            for page_num, html in zip(batch, results):
                if html:
                    docs = parse_listing_page(html, page_num)
                    for doc in docs:
                        c.execute("""
                            INSERT OR IGNORE INTO documents 
                            (id, doc_number, title, issue_date, pdf_url, source_page, created_at)
                            VALUES (?, ?, ?, ?, ?, ?, ?)
                        """, (doc["id"], doc["doc_number"], doc["title"],
                              doc["issue_date"], doc["pdf_url"], page_num,
                              datetime.now().isoformat()))

                    c.execute("""
                        INSERT OR REPLACE INTO pages (page_num, status, doc_count, updated_at)
                        VALUES (?, 'completed', ?, ?)
                    """, (page_num, len(docs), datetime.now().isoformat()))
                    batch_docs += len(docs)
                else:
                    c.execute("""
                        INSERT OR REPLACE INTO pages (page_num, status, doc_count, updated_at)
                        VALUES (?, 'failed', 0, ?)
                    """, (page_num, datetime.now().isoformat()))

            conn.commit()
            conn.close()
            total_docs += batch_docs

            elapsed = time.time() - start
            progress = min(i + CHUNK_SIZE_PAGES, len(pages_todo))
            print(f"  [{progress}/{len(pages_todo)}] +{batch_docs} docs "
                  f"({elapsed:.0f}s elapsed)")

            await asyncio.sleep(1)  # Be polite

    print(f"\n[Phase 1] DONE — {total_docs} new documents indexed")


# ============================================================
# PHASE 2: DOWNLOAD PDFs
# ============================================================
async def download_pdf(client: httpx.AsyncClient, doc: dict,
                       semaphore: asyncio.Semaphore) -> Optional[str]:
    """Download a single PDF and return the local file path."""
    async with semaphore:
        pdf_url = doc["pdf_url"]
        doc_id = doc["id"]
        local_path = os.path.join(FILES_DIR, f"{doc_id}.pdf")

        if os.path.exists(local_path) and os.path.getsize(local_path) > 100:
            return local_path

        for attempt in range(3):
            try:
                resp = await client.get(pdf_url, timeout=60.0)
                if resp.status_code == 200 and len(resp.content) > 100:
                    with open(local_path, "wb") as f:
                        f.write(resp.content)
                    return local_path
                print(f"  [!] PDF {doc_id}: HTTP {resp.status_code}")
            except Exception as e:
                print(f"  [!] PDF {doc_id} attempt {attempt+1}: {e}")
                await asyncio.sleep(2 * (attempt + 1))
        return None


async def phase2_download_pdfs():
    """Phase 2: Download all PDFs for documents that have PDF links."""
    print("\n" + "=" * 60)
    print("PHASE 2: DOWNLOADING PDFs")
    print("=" * 60)

    conn = get_db()
    c = conn.cursor()
    c.execute("""
        SELECT id, doc_number, title, pdf_url 
        FROM documents 
        WHERE pdf_url IS NOT NULL AND pdf_url != '' AND pdf_status = 'pending'
    """)
    docs = [dict(row) for row in c.fetchall()]
    conn.close()

    print(f"[Phase 2] {len(docs)} PDFs to download")
    if not docs:
        print("[Phase 2] All PDFs already downloaded!")
        return

    semaphore = asyncio.Semaphore(CONCURRENT_REQUESTS)
    downloaded = 0
    failed = 0
    start = time.time()

    async with httpx.AsyncClient(headers=BROWSER_HEADERS, follow_redirects=True) as client:
        for i in range(0, len(docs), PDF_BATCH_SIZE):
            batch = docs[i:i + PDF_BATCH_SIZE]
            tasks = [download_pdf(client, doc, semaphore) for doc in batch]
            results = await asyncio.gather(*tasks)

            conn = get_db()
            c = conn.cursor()
            for doc, path in zip(batch, results):
                if path:
                    c.execute("""
                        UPDATE documents SET pdf_status='downloaded', pdf_path=?
                        WHERE id=?
                    """, (path, doc["id"]))
                    downloaded += 1
                else:
                    c.execute("""
                        UPDATE documents SET pdf_status='failed' WHERE id=?
                    """, (doc["id"],))
                    failed += 1
            conn.commit()
            conn.close()

            progress = min(i + PDF_BATCH_SIZE, len(docs))
            elapsed = time.time() - start
            print(f"  [{progress}/{len(docs)}] OK:{downloaded} ERR:{failed} "
                  f"({elapsed:.0f}s)")

            await asyncio.sleep(0.5)

    print(f"\n[Phase 2] DONE — {downloaded} downloaded, {failed} failed")


# ============================================================
# PHASE 3: EXTRACT TEXT + CHUNK + SAVE JSON
# ============================================================
def extract_text_from_pdf(pdf_path: str) -> Tuple[str, int]:
    """Extract text from PDF using PyMuPDF. Returns (text, page_count)."""
    if not HAS_PYMUPDF:
        raise ImportError("pymupdf is required for Phase 3")

    doc = fitz.open(pdf_path)
    pages = []
    for i, page in enumerate(doc):
        page_text = page.get_text().strip()
        if page_text:
            pages.append(f"[[PAGE_{i+1}]]\n{page_text}")
    page_count = len(doc)
    doc.close()
    return "\n\n".join(pages), page_count


def detect_legal_structure(text: str, doc_number: str = "") -> Dict[str, Any]:
    """Detect Điều/Khoản/Chương and Issuing Authority."""
    meta = {
        "dieu": None, "khoan": None, "chuong": None, "page": None,
        "issuing_authority": None
    }

    # 1. Map Authority from Document Number
    if doc_number:
        auth_map = {
            "-TTg": "Thủ tướng Chính phủ",
            "-CP": "Chính phủ",
            "-QH": "Quốc hội",
            "-CTN": "Chủ tịch nước",
            "-BNV": "Bộ Nội vụ",
            "-BTC": "Bộ Tài chính",
            "-BTP": "Bộ Tư pháp",
            "-VPCP": "Văn phòng Chính phủ",
            "/QH": "Quốc hội"
        }
        for suffix, auth in auth_map.items():
            if suffix in doc_number.upper():
                meta["issuing_authority"] = auth
                break

    # 2. Detect page
    page_match = re.search(r'\[\[PAGE_(\d+)\]\]', text)
    if page_match:
        meta["page"] = int(page_match.group(1))

    # 3. Detect Chương
    chuong_match = re.search(r'Chương\s+([IVXLCDM]+|\d+)', text, re.IGNORECASE)
    if chuong_match:
        meta["chuong"] = chuong_match.group(1)

    # 4. Detect Điều (Support "Điều 1.", "Điều 1:")
    dieu_match = re.search(r'Điều\s+(\d+)', text, re.IGNORECASE)
    if dieu_match:
        meta["dieu"] = int(dieu_match.group(1))

    # 5. Detect Khoản (Support "1.", "2.")
    khoan_match = re.search(r'^(\d+)\.\s', text.strip())
    if khoan_match:
        meta["khoan"] = khoan_match.group(1)

    return meta


def chunk_text_simple(text: str, source_id: str, doc_meta: Dict,
                      target_tokens: int = TARGET_TOKENS,
                      overlap: int = OVERLAP_SENTENCES) -> List[Dict]:
    """Chunk text into pieces, matching DocMind's Chunk format."""
    # Clean page markers for splitting but keep for page detection
    sentences = re.split(r'(?<=[.!?])\s+', text)
    chunks = []
    buffer = []
    buf_tokens = 0
    chunk_idx = 0

    for sentence in sentences:
        tokens = len(sentence.split())
        if buf_tokens + tokens > target_tokens and buffer:
            chunk_text_content = " ".join(buffer)
            legal = detect_legal_structure(chunk_text_content, doc_meta.get("doc_number", ""))
            # Clean page markers from output text
            clean_text = re.sub(r'\[\[PAGE_\d+\]\]\s*', '', chunk_text_content).strip()

            if clean_text and len(clean_text) > 10:
                chunks.append({
                    "id": f"{source_id}_{chunk_idx}",
                    "source_id": source_id,
                    "index": chunk_idx,
                    "text": clean_text,
                    "token_count": len(clean_text.split()),
                    "page": legal["page"],
                    "char_start": None,
                    "char_end": None,
                    "dieu": legal["dieu"],
                    "khoan": legal["khoan"],
                    "chuong": legal["chuong"],
                    "document_number": doc_meta.get("doc_number"),
                    "issuance_date": doc_meta.get("issue_date"),
                    "issuing_authority": legal["issuing_authority"],
                })
                chunk_idx += 1

            buffer = buffer[-overlap:] if len(buffer) > overlap else buffer
            buf_tokens = sum(len(s.split()) for s in buffer)

        buffer.append(sentence)
        buf_tokens += tokens

    # Last chunk
    if buffer:
        chunk_text_content = " ".join(buffer)
        legal = detect_legal_structure(chunk_text_content, doc_meta.get("doc_number", ""))
        clean_text = re.sub(r'\[\[PAGE_\d+\]\]\s*', '', chunk_text_content).strip()
        if clean_text and len(clean_text) > 10:
            chunks.append({
                "id": f"{source_id}_{chunk_idx}",
                "source_id": source_id,
                "index": chunk_idx,
                "text": clean_text,
                "token_count": len(clean_text.split()),
                "page": legal["page"],
                "char_start": None, "char_end": None,
                "dieu": legal["dieu"],
                "khoan": legal["khoan"],
                "chuong": legal["chuong"],
                "document_number": doc_meta.get("doc_number"),
                "issuance_date": doc_meta.get("issue_date"),
                "issuing_authority": legal["issuing_authority"],
            })

    return chunks


def create_metadata_chunk(doc: Dict) -> List[Dict]:
    """For docs without PDF, create a minimal chunk from listing metadata."""
    source_id = doc["id"]
    text = f"{doc['doc_number']} — {doc['title']}"
    if doc.get("issue_date"):
        text += f" (Ban hành: {doc['issue_date']})"

    # Try to get authority for metadata chunk too
    legal_meta = detect_legal_structure("", doc.get("doc_number", ""))

    return [{
        "id": f"{source_id}_0",
        "source_id": source_id,
        "index": 0,
        "text": text,
        "token_count": len(text.split()),
        "page": None, "char_start": None, "char_end": None,
        "dieu": None, "khoan": None, "chuong": None,
        "document_number": doc.get("doc_number"),
        "issuance_date": doc.get("issue_date"),
        "issuing_authority": legal_meta["issuing_authority"],
    }]


def save_chunk_json(source_id: str, chunks: List[Dict]):
    """Save chunks to JSON file in DocMind format."""
    output = {"source_id": source_id, "chunks": chunks}
    path = os.path.join(CHUNKS_DIR, f"{source_id}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    return path


def phase3_extract_and_chunk():
    """Phase 3: Extract text from PDFs, chunk, save as JSON."""
    print("\n" + "=" * 60)
    print("PHASE 3: EXTRACTING TEXT & CREATING CHUNKS")
    print("=" * 60)

    if not HAS_PYMUPDF:
        print("[ERROR] pymupdf is required. Install: pip install pymupdf")
        return

    conn = get_db()
    c = conn.cursor()

    # Process downloaded PDFs first
    c.execute("""
        SELECT id, doc_number, title, issue_date, pdf_url, pdf_path
        FROM documents
        WHERE pdf_status='downloaded' AND chunk_status='pending'
    """)
    pdf_docs = [dict(row) for row in c.fetchall()]

    # Also process docs without PDFs (metadata-only chunks)
    c.execute("""
        SELECT id, doc_number, title, issue_date, pdf_url
        FROM documents
        WHERE (pdf_url IS NULL OR pdf_url='') AND chunk_status='pending'
    """)
    no_pdf_docs = [dict(row) for row in c.fetchall()]
    conn.close()

    total = len(pdf_docs) + len(no_pdf_docs)
    print(f"[Phase 3] {len(pdf_docs)} PDFs + {len(no_pdf_docs)} metadata-only = {total} total")

    if total == 0:
        print("[Phase 3] All documents already processed!")
        return

    processed = 0
    errors = 0
    start = time.time()

    # Process PDFs
    for i, doc in enumerate(pdf_docs):
        try:
            pdf_path = doc["pdf_path"]
            if not pdf_path or not os.path.exists(pdf_path):
                raise FileNotFoundError(f"PDF not found: {pdf_path}")

            text, page_count = extract_text_from_pdf(pdf_path)

            if len(text.strip()) < 50:
                # Very little text — likely scanned, create metadata chunk
                chunks = create_metadata_chunk(doc)
            else:
                chunks = chunk_text_simple(text, doc["id"], doc)

            if not chunks:
                chunks = create_metadata_chunk(doc)

            save_chunk_json(doc["id"], chunks)

            conn = get_db()
            c = conn.cursor()
            c.execute("UPDATE documents SET chunk_status='completed' WHERE id=?",
                      (doc["id"],))
            conn.commit()
            conn.close()
            processed += 1

        except Exception as e:
            conn = get_db()
            c = conn.cursor()
            c.execute("UPDATE documents SET chunk_status='failed' WHERE id=?",
                      (doc["id"],))
            conn.commit()
            conn.close()
            errors += 1
            if errors <= 10:
                print(f"  [!] Error {doc['id']}: {e}")

        if (i + 1) % 100 == 0:
            elapsed = time.time() - start
            print(f"  [PDF {i+1}/{len(pdf_docs)}] OK:{processed} ERR:{errors} ({elapsed:.0f}s)")

    # Process metadata-only docs
    for i, doc in enumerate(no_pdf_docs):
        try:
            chunks = create_metadata_chunk(doc)
            save_chunk_json(doc["id"], chunks)

            conn = get_db()
            c = conn.cursor()
            c.execute("UPDATE documents SET chunk_status='completed' WHERE id=?",
                      (doc["id"],))
            conn.commit()
            conn.close()
            processed += 1
        except Exception as e:
            errors += 1

        if (i + 1) % 500 == 0:
            print(f"  [Meta {i+1}/{len(no_pdf_docs)}] OK:{processed} ERR:{errors}")

    elapsed = time.time() - start
    print(f"\n[Phase 3] DONE — {processed} chunked, {errors} errors ({elapsed:.0f}s)")


# ============================================================
# UPDATE SOURCES.JSON
# ============================================================
def update_sources_json():
    """Update sources.json with all successfully chunked documents."""
    print("\n[Updating sources.json...]")

    # Load existing sources
    existing_sources = {}
    if os.path.exists(SOURCES_PATH):
        with open(SOURCES_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
            for s in data.get("sources", []):
                existing_sources[s["id"]] = s

    conn = get_db()
    c = conn.cursor()
    c.execute("""
        SELECT id, doc_number, title, issue_date, pdf_url, pdf_path
        FROM documents WHERE chunk_status='completed'
    """)
    docs = [dict(row) for row in c.fetchall()]
    conn.close()

    new_count = 0
    for doc in docs:
        if doc["id"] in existing_sources:
            continue

        # Count chunks
        chunk_path = os.path.join(CHUNKS_DIR, f"{doc['id']}.json")
        chunk_count = 0
        word_count = 0
        if os.path.exists(chunk_path):
            with open(chunk_path, "r", encoding="utf-8") as f:
                chunk_data = json.load(f)
                chunks = chunk_data.get("chunks", [])
                chunk_count = len(chunks)
                word_count = sum(c.get("token_count", 0) for c in chunks)

        source = {
            "id": doc["id"],
            "name": doc["title"][:200] if doc["title"] else doc["doc_number"],
            "type": "pdf" if doc["pdf_url"] else "text",
            "active": True,
            "chunk_count": chunk_count,
            "word_count": word_count,
            "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "meta": {
                "url": doc.get("pdf_url"),
                "page_count": None,
                "language": "vi",
                "local_path": doc.get("pdf_path"),
                "document_number": doc.get("doc_number"),
                "issuance_date": doc.get("issue_date"),
                "issuing_authority": None,
            }
        }
        existing_sources[doc["id"]] = source
        new_count += 1

    output = {"sources": list(existing_sources.values())}
    with open(SOURCES_PATH, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"  Added {new_count} new sources (total: {len(existing_sources)})")


# ============================================================
# STATUS REPORT
# ============================================================
def show_status():
    print("\n" + "=" * 60)
    print("CRAWL STATUS REPORT")
    print("=" * 60)

    if not os.path.exists(DB_PATH):
        print("No crawl database found. Run the crawler first.")
        return

    conn = get_db()
    c = conn.cursor()

    c.execute("SELECT COUNT(*) FROM pages WHERE status='completed'")
    pages_done = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM pages WHERE status='failed'")
    pages_fail = c.fetchone()[0]

    c.execute("SELECT COUNT(*) FROM documents")
    total_docs = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM documents WHERE pdf_url IS NOT NULL AND pdf_url != ''")
    with_pdf = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM documents WHERE pdf_status='downloaded'")
    pdf_done = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM documents WHERE pdf_status='failed'")
    pdf_fail = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM documents WHERE chunk_status='completed'")
    chunks_done = c.fetchone()[0]

    conn.close()

    # Count JSON files
    json_files = len([f for f in os.listdir(CHUNKS_DIR) if f.endswith(".json")])

    print(f"  Pages crawled:     {pages_done}/{MAX_PAGES} ({pages_fail} failed)")
    print(f"  Documents found:   {total_docs} ({with_pdf} with PDF)")
    print(f"  PDFs downloaded:   {pdf_done}/{with_pdf} ({pdf_fail} failed)")
    print(f"  Chunks created:    {chunks_done}/{total_docs}")
    print(f"  JSON files:        {json_files} in {CHUNKS_DIR}")
    print("=" * 60)


# ============================================================
# MAIN
# ============================================================
async def main():
    parser = argparse.ArgumentParser(description="DocMind Full Crawler")
    parser.add_argument("--phase", type=int, choices=[1, 2, 3],
                        help="Run specific phase (1=listings, 2=PDFs, 3=chunks)")
    parser.add_argument("--status", action="store_true", help="Show progress")
    parser.add_argument("--pages", type=int, default=MAX_PAGES,
                        help=f"Max pages to crawl (default: {MAX_PAGES})")
    args = parser.parse_args()

    init_db()

    if args.status:
        show_status()
        return

    start = time.time()

    if args.phase is None or args.phase == 1:
        await phase1_crawl_listings(max_pages=args.pages)

    if args.phase is None or args.phase == 2:
        await phase2_download_pdfs()

    if args.phase is None or args.phase == 3:
        phase3_extract_and_chunk()
        update_sources_json()

    duration = time.time() - start
    print(f"\n{'=' * 60}")
    print(f"TOTAL TIME: {duration:.0f}s ({duration/60:.1f} min)")
    print(f"{'=' * 60}")
    show_status()


if __name__ == "__main__":
    asyncio.run(main())
