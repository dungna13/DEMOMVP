"""
DocMind Full Crawler — Ultra-Fast & 100% Offline
Uses Regex-based Legal Parsing (No Gemini API required).
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
from services.ingestor import ingest_pdf_smart

# ============================================================
# CONFIGURATION
# ============================================================
BASE_URL = "https://vanban.chinhphu.vn/he-thong-van-ban?mode=0"
MAX_PAGES = 1950 
REQUEST_TIMEOUT = 60.0

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
# LOCAL LEGAL PARSER (Regex based - No API needed)
# ============================================================
def local_legal_chunker(text: str, doc_id: str, doc_number: str, issue_date: str) -> Dict[str, Any]:
    """
    Parses Vietnamese legal text into chunks with 'dieu', 'khoan' metadata.
    100% Local, 0 tokens.
    """
    # Split text by "Điều X."
    pattern = r'(?m)^(Điều\s+\d+[\.:\s])'
    parts = re.split(pattern, text)
    
    chunks = []
    header_text = parts[0].strip()
    
    # Add header (preamble) if exists
    if header_count := len(header_text) > 20:
        chunks.append({
            "id": f"{doc_id}_header",
            "source_id": doc_id,
            "index": 0,
            "text": header_text[:2000], # Cap size
            "token_count": len(header_text.split()),
            "page": None, "char_start": None, "char_end": None,
            "dieu": None, "khoan": None, "chuong": None,
            "document_number": doc_number,
            "issuance_date": issue_date,
            "issuing_authority": "Văn bản Chính phủ"
        })

    # Process "Điều X." parts
    current_index = len(chunks)
    for i in range(1, len(parts), 2):
        dieu_header = parts[i].strip()
        dieu_content = parts[i+1].strip() if i+1 < len(parts) else ""
        
        # Extract the number from "Điều X."
        dieu_num_match = re.search(r'\d+', dieu_header)
        dieu_num = int(dieu_num_match.group()) if dieu_num_match else None
        
        full_dieu_text = f"{dieu_header} {dieu_content}"
        
        chunks.append({
            "id": f"{doc_id}_{current_index}",
            "source_id": doc_id,
            "index": current_index,
            "text": full_dieu_text[:3000], # Prevent massive chunks
            "token_count": len(full_dieu_text.split()),
            "page": None, "char_start": None, "char_end": None,
            "dieu": dieu_num,
            "khoan": None, "chuong": None,
            "document_number": doc_number,
            "issuance_date": issue_date,
            "issuing_authority": "Văn bản Chính phủ"
        })
        current_index += 1

    return {
        "source_id": doc_id,
        "chunks": chunks
    }

# ============================================================
# CORE LOGIC
# ============================================================
def load_sources():
    if os.path.exists(SOURCES_PATH):
        try:
            with open(SOURCES_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data if isinstance(data, list) else []
        except: return []
    return []

def save_sources(sources):
    with open(SOURCES_PATH, "w", encoding="utf-8") as f:
        json.dump(sources, f, ensure_ascii=False, indent=2)

def is_already_processed(doc_id):
    return os.path.exists(os.path.join(CHUNKS_DIR, f"{doc_id}.json"))

def parse_listing_page(html: str, page_num: int) -> List[Dict[str, Any]]:
    soup = BeautifulSoup(html, "html.parser")
    docs = []
    rows = soup.find_all("tr")
    for row in rows:
        cells = row.find_all("td")
        if len(cells) < 3: continue
        c0_text = cells[0].get_text(strip=True)
        idx_number, idx_date, idx_title = (1, 2, 3) if (c0_text.isdigit() and len(c0_text) <= 3) else (0, 1, 2)
        if len(cells) <= idx_title: continue
        doc_number = cells[idx_number].get_text(strip=True)
        if not doc_number or doc_number in ("Số ký hiệu", "STT"): continue
        issue_date = cells[idx_date].get_text(strip=True)
        title, pdf_url = "", None
        for link in cells[idx_title].find_all("a"):
            href = link.get("href", "")
            if "datafiles.chinhphu.vn" in href and href.endswith(".pdf"):
                pdf_url = "https:" + href if href.startswith("//") else href
            elif link.get_text(strip=True) and "đính kèm" not in link.get_text(strip=True).lower():
                title = link.get_text(strip=True)
        if not title: title = cells[idx_title].get_text(strip=True)[:500]
        safe_num = re.sub(r'[^a-zA-Z0-9]', '', doc_number).lower()
        doc_id = f"gov-{safe_num}-{hashlib.md5(doc_number.encode()).hexdigest()[:6]}"
        docs.append({"id": doc_id, "doc_number": doc_number, "title": title, "issue_date": issue_date, "pdf_url": pdf_url})
    return docs

async def process_document(client, doc, sources_dict):
    doc_id = doc["id"]
    if is_already_processed(doc_id): return True
    if not doc["pdf_url"]: return False

    try:
        resp = await client.get(doc["pdf_url"])
        if resp.status_code != 200: return False
        
        import base64
        b64_pdf = base64.b64encode(resp.content).decode("utf-8")
        text, was_ocr = await ingest_pdf_smart(b64_pdf, {"document_number": doc["doc_number"], "issuance_date": doc["issue_date"]})

        # USE LOCAL CHUNKER (0 API CALLS)
        result_json = local_legal_chunker(text, doc_id, doc["doc_number"], doc["issue_date"])
        
        with open(os.path.join(CHUNKS_DIR, f"{doc_id}.json"), "w", encoding="utf-8") as f:
            json.dump(result_json, f, ensure_ascii=False, indent=2)

        sources_dict[doc_id] = {
            "id": doc_id, "name": doc["doc_number"], "type": "pdf",
            "content": doc["title"], "added_at": datetime.now().isoformat()
        }
        print(f"   [Done] {doc['doc_number']} ({'OCR' if was_ocr else 'Text'})")
        return True
    except Exception as e:
        print(f"   [Error] {doc['doc_number']}: {e}")
        return False

async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--pages", type=int, default=120)
    parser.add_argument("--limit", type=int, default=6000)
    args = parser.parse_args()

    conn = sqlite3.connect(DB_PATH)
    conn.executescript("CREATE TABLE IF NOT EXISTS pages (page_num INTEGER PRIMARY KEY, status TEXT); CREATE TABLE IF NOT EXISTS documents (id TEXT PRIMARY KEY, doc_number TEXT, title TEXT, issue_date TEXT, pdf_url TEXT);")
    
    print(f"\n[PHASE 1] Crawling {args.pages} pages...")
    async with httpx.AsyncClient(headers=BROWSER_HEADERS, follow_redirects=True, timeout=30.0) as client:
        for p in range(1, args.pages + 1):
            resp = await client.get(f"{BASE_URL}&p={p}")
            if resp.status_code == 200:
                docs = parse_listing_page(resp.text, p)
                for d in docs:
                    conn.execute("INSERT OR IGNORE INTO documents VALUES (?,?,?,?,?)", (d["id"], d["doc_number"], d["title"], d["issue_date"], d["pdf_url"]))
                conn.commit()
                if p % 10 == 0: print(f"   Crawled page {p}")

    print(f"\n[PHASE 2] Processing docs (Limit: {args.limit})...")
    c = conn.cursor()
    c.execute("SELECT * FROM documents")
    all_docs = [dict(zip(["id", "doc_number", "title", "issue_date", "pdf_url"], row)) for row in c.fetchall()]
    
    sources_dict = {s["id"]: s for s in load_sources()}
    current_total = len(sources_dict)

    async with httpx.AsyncClient(headers=BROWSER_HEADERS, follow_redirects=True, timeout=60.0) as client:
        for i in range(0, len(all_docs), 5):
            if current_total >= args.limit: break
            batch = all_docs[i:i+5]
            tasks = [process_document(client, d, sources_dict) for d in batch]
            results = await asyncio.gather(*tasks)
            current_total += sum(1 for r in results if r is True)
            save_sources(list(sources_dict.values()))
            if i % 25 == 0: print(f"   Progress: {current_total}/{args.limit}")

    print("\n--- ALL DONE (100% OFFLINE) ---")

if __name__ == "__main__":
    asyncio.run(main())
