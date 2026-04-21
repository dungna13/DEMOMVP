"""
DocMind Full Crawler — Pro Version
Integrated with Main App, EasyOCR (Local AI), and Smart Skipping.
"""

import asyncio
import sqlite3
import os
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

# Import our high-quality ingestor logic
from services.ingestor import ingest_pdf_smart, get_text_from_source

# ============================================================
# CONFIGURATION
# ============================================================
BASE_URL = "https://vanban.chinhphu.vn/he-thong-van-ban?mode=0"
MAX_PAGES = 1950 # Total pages on the portal
REQUEST_TIMEOUT = 60.0

# Path alignment with the main app
BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BACKEND_DIR, "data")
DB_PATH = os.path.join(DATA_DIR, "full_crawl_progress.db")
CHUNKS_DIR = os.path.join(DATA_DIR, "chunks")
FILES_DIR = os.path.join(DATA_DIR, "files")
SOURCES_PATH = os.path.join(DATA_DIR, "sources.json")

BROWSER_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept-Language": "vi-VN,vi;q=0.9,en;q=0.8",
}

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
    """)
    conn.commit()
    conn.close()

# ============================================================
# UTILITIES
# ============================================================
def load_sources():
    if os.path.exists(SOURCES_PATH):
        try:
            with open(SOURCES_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except: return []
    return []

def save_sources(sources):
    with open(SOURCES_PATH, "w", encoding="utf-8") as f:
        json.dump(sources, f, ensure_ascii=False, indent=2)

def is_already_processed(doc_id):
    """Check if the document is already in our main storage."""
    pdf_exists = os.path.exists(os.path.join(FILES_DIR, f"{doc_id}.pdf"))
    chunk_exists = os.path.exists(os.path.join(CHUNKS_DIR, f"{doc_id}.json"))
    return pdf_exists and chunk_exists

# ============================================================
# PHASE 1: CRAWL LISTINGS
# ============================================================
def parse_listing_page(html: str, page_num: int) -> List[Dict[str, Any]]:
    soup = BeautifulSoup(html, "html.parser")
    docs = []
    rows = soup.find_all("tr")

    for row in rows:
        cells = row.find_all("td")
        if len(cells) < 3: continue

        c0_text = cells[0].get_text(strip=True)
        if c0_text.isdigit() and len(c0_text) <= 3:
            idx_number, idx_date, idx_title = 1, 2, 3
        else:
            idx_number, idx_date, idx_title = 0, 1, 2

        if len(cells) <= idx_title: continue

        doc_number = cells[idx_number].get_text(strip=True)
        if not doc_number or doc_number in ("Số ký hiệu", "STT"): continue

        issue_date = cells[idx_date].get_text(strip=True)
        title = ""
        pdf_url = None
        for link in cells[idx_title].find_all("a"):
            href = link.get("href", "")
            if "datafiles.chinhphu.vn" in href and href.endswith(".pdf"):
                pdf_url = "https:" + href if href.startswith("//") else href
            elif link.get_text(strip=True) and "đính kèm" not in link.get_text(strip=True).lower():
                title = link.get_text(strip=True)

        if not title: title = cells[idx_title].get_text(strip=True)[:500]
        
        # Consistent ID based on Doc Number to avoid duplicates across crawls
        safe_num = re.sub(r'[^a-zA-Z0-9]', '', doc_number).lower()
        doc_id = hashlib.md5(f"{doc_number}".encode("utf-8")).hexdigest()[:10]
        final_id = f"gov-{safe_num}-{doc_id}"

        docs.append({
            "id": final_id, "doc_number": doc_number, "title": title,
            "issue_date": issue_date, "pdf_url": pdf_url, "source_page": page_num,
        })
    return docs

async def phase1_crawl_listings(max_pages: int):
    print(f"\n[Phase 1] Crawling listings up to page {max_pages}...")
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT page_num FROM pages WHERE status='completed'")
    completed = {row[0] for row in c.fetchall()}
    pages_todo = [p for p in range(1, max_pages + 1) if p not in completed]
    conn.close()

    if not pages_todo: 
        print("   All listing pages already crawled.")
        return

    async with httpx.AsyncClient(headers=BROWSER_HEADERS, follow_redirects=True, timeout=30.0) as client:
        for i in range(0, len(pages_todo), 10):
            batch = pages_todo[i:i+10]
            tasks = [client.get(f"{BASE_URL}&p={p}") for p in batch]
            responses = await asyncio.gather(*tasks, return_exceptions=True)
            
            conn = get_db()
            c = conn.cursor()
            for p, resp in zip(batch, responses):
                if isinstance(resp, httpx.Response) and resp.status_code == 200:
                    docs = parse_listing_page(resp.text, p)
                    for d in docs:
                        c.execute("INSERT OR IGNORE INTO documents (id, doc_number, title, issue_date, pdf_url, source_page, created_at) VALUES (?,?,?,?,?,?,?)",
                                  (d["id"], d["doc_number"], d["title"], d["issue_date"], d["pdf_url"], p, datetime.now().isoformat()))
                    c.execute("INSERT OR REPLACE INTO pages (page_num, status, doc_count, updated_at) VALUES (?, 'completed', ?, ?)", (p, len(docs), datetime.now().isoformat()))
                else:
                    print(f"   Failed to crawl page {p}")
            conn.commit()
            conn.close()
            print(f"   Processed pages {batch[0]}-{batch[-1]}")
            await asyncio.sleep(0.5)

# ============================================================
# PHASE 2: SMART DOWNLOAD & PROCESS
# ============================================================
async def process_document(client, doc, sources_dict):
    doc_id = doc["id"]
    
    # --- SKIP CHECK ---
    if is_already_processed(doc_id) and doc_id in sources_dict:
        # print(f"   [Skipped] {doc['doc_number']} (Already exists)")
        return True

    if not doc["pdf_url"]: return False

    try:
        # 1. Download
        resp = await client.get(doc["pdf_url"])
        if resp.status_code != 200: return False
        
        pdf_path = os.path.join(FILES_DIR, f"{doc_id}.pdf")
        with open(pdf_path, "wb") as f: f.write(resp.content)

        # 2. Extract Text (Using our high-quality Ingestor with EasyOCR)
        import base64
        b64_pdf = base64.b64encode(resp.content).decode("utf-8")
        doc_info = {"document_number": doc["doc_number"], "issuance_date": doc["issue_date"]}
        
        text, was_ocr = await ingest_pdf_smart(b64_pdf, doc_info)

        # 3. Save Chunks (Format perfectly aligned with sample JSON)
        from services.legal_processor import process_legal_document
        # This function already handles the structure: source_id, chunks, dieu, khoan, etc.
        chunks = await process_legal_document(text) 
        
        # Ensure metadata from crawl (doc_number, date) is merged into chunks if legal_processor missed it
        if chunks and "chunks" in chunks:
            for chunk in chunks["chunks"]:
                chunk["source_id"] = doc_id
                # Fill missing metadata from crawl info
                if not chunk.get("document_number"): chunk["document_number"] = doc["doc_number"]
                if not chunk.get("issuance_date"): chunk["issuance_date"] = doc["issue_date"]
                
            # Overwrite the file with the corrected/merged metadata
            chunk_path = os.path.join(CHUNKS_DIR, f"{doc_id}.json")
            with open(chunk_path, "w", encoding="utf-8") as f:
                json.dump(chunks, f, ensure_ascii=False, indent=2)
        sources_dict[doc_id] = {
            "id": doc_id,
            "name": doc["doc_number"],
            "type": "pdf",
            "content": doc["title"],
            "added_at": doc["created_at"] or datetime.now().isoformat()
        }
        
        print(f"   [Done] {doc['doc_number']} ({'OCR' if was_ocr else 'Text'})")
        return True
    except Exception as e:
        print(f"   [Error] {doc['doc_number']}: {e}")
        return False

async def phase2_full_processing(limit: int):
    print(f"\n[Phase 2] Downloading and Processing Documents (Limit: {limit})...")
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT * FROM documents WHERE pdf_url IS NOT NULL")
    docs = [dict(row) for row in c.fetchall()]
    conn.close()

    sources_list = load_sources()
    sources_dict = {s["id"]: s for s in sources_list}
    
    processed_count = 0
    # Already count what we have in sources.json as processed
    current_total = len(sources_dict)
    
    print(f"   Currently have {current_total} sources. Target limit: {limit}")

    async with httpx.AsyncClient(headers=BROWSER_HEADERS, follow_redirects=True, timeout=60.0) as client:
        for i in range(0, len(docs), 5): # Process in batches of 5
            if current_total >= limit:
                print(f"\n   [Reached Limit] Total sources reached {limit}. Stopping.")
                break
                
            batch = docs[i:i+5]
            tasks = [process_document(client, doc, sources_dict) for doc in batch]
            results = await asyncio.gather(*tasks)
            
            # Increment count by number of newly successful documents
            newly_added = sum(1 for r in results if r is True)
            current_total += newly_added
            
            # Periodically save progress to sources.json
            save_sources(list(sources_dict.values()))
            if (i+5) % 25 == 0:
                print(f"   Progress: {current_total}/{limit} documents in system.")

async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--pages", type=int, default=120) # 120 pages ~ 6000 docs
    parser.add_argument("--limit", type=int, default=6000) # Stop at 6000
    args = parser.parse_args()

    init_db()
    await phase1_crawl_listings(args.pages)
    await phase2_full_processing(args.limit)
    print("\n--- FULL CRAWL COMPLETE ---")

if __name__ == "__main__":
    asyncio.run(main())
