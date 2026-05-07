"""
ingestion.py — Nap du lieu tu folder chunks vao SQLite
Sua loi binding SQL va hoan thien logic dedup.
"""

import json
import os
import glob
import re
import hashlib
from collections import defaultdict
from database import get_db, is_empty

CHUNKS_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "chunks"))
DATA_DIR = os.path.join(os.path.dirname(__file__), "data")

def parse_doc_type(doc_number: str) -> str:
    n = doc_number.upper()
    if re.search(r"\d+/QH\d+", n): return "luat"
    if re.search(r"/NQ-UBTVQH|/NQ-QH", n): return "nghi_quyet"
    if re.search(r"/ND-CP|/N\xD0-CP", n): return "nghi_dinh"
    if re.search(r"/TT-", n): return "thong_tu"
    if re.search(r"/QD-TTG|/Q\xD0-TTG", n): return "quyet_dinh"
    if re.search(r"/QD-|/Q\xD0-", n): return "quyet_dinh"
    if re.search(r"/NQ-", n): return "nghi_quyet"
    if re.search(r"/CT-", n): return "chi_thi"
    return "cong_van"

def clean_text(text: str) -> str:
    if not text: return ""
    t = re.sub(r'\[\[PAGE_\d+\]\]', '', text)
    t = re.sub(r'\r', '', t)
    t = re.sub(r'\n{3,}', '\n\n', t)
    return t.strip()

def get_text_hash(text: str) -> str:
    normalized = " ".join(text.split())
    return hashlib.md5(normalized.encode('utf-8')).hexdigest()

def build_title(doc_number: str, issuing_authority: str, chunks: list) -> str:
    doc_type = parse_doc_type(doc_number)
    type_map = {
        "quyet_dinh": "Quyet dinh", "nghi_dinh": "Nghi dinh",
        "thong_tu": "Thong tu", "luat": "Luat",
        "nghi_quyet": "Nghi quyet", "chi_thi": "Chi thi", "cong_van": "Cong van",
    }
    type_label = type_map.get(doc_type, "Van ban")
    header = chunks[0] if chunks else {}
    text = clean_text(header.get("text", ""))
    match = re.search(r'(QUY\xc9T\s+\x10\xcfNH|NGH\xcc\s+\x10\xccNH|TH\xd4NG\s+T\u01af|LU\xcaT)\s*\n(.*?)\n', text, re.IGNORECASE | re.DOTALL)
    if match:
        snippet = match.group(2).strip().replace("\n", " ")
        if len(snippet) > 10: return f"{type_label} {doc_number}: {snippet}"
    snippet = text[:150].replace("\n", " ")
    if snippet: return f"{type_label} {doc_number}: {snippet}..."
    return f"{type_label} so {doc_number}"

def build_content_markdown(chunks: list, doc_number: str) -> str:
    lines = [f"# Van ban so {doc_number}\n"]
    for chunk in chunks:
        text = clean_text(chunk.get("text", ""))
        if not text: continue
        dieu = chunk.get("dieu")
        khoan = chunk.get("khoan")
        if chunk.get("index") == 0:
            lines.append(f"\n{text}\n")
        elif dieu and not khoan:
            if re.match(r'^Di\u1ec1u \d+', text, re.I): lines.append(f"\n## {text}\n")
            else: lines.append(f"\n## Dieu {dieu}\n\n{text}\n")
        elif dieu and khoan:
            lines.append(f"\n### Khoan {khoan} (Dieu {dieu})\n\n{text}\n")
        else:
            lines.append(f"\n{text}\n")
    return "\n".join(lines)

def ingest_document(doc_number: str, chunks: list) -> int:
    if not chunks: return -1
    chunks.sort(key=lambda x: x.get("index", 0))
    first = chunks[0]
    issuing_date = first.get("issuance_date", "")
    issuing_authority = first.get("issuing_authority", "")
    doc_type = parse_doc_type(doc_number)
    title = build_title(doc_number, issuing_authority, chunks)
    content_markdown = build_content_markdown(chunks, doc_number)
    summary = content_markdown[len(f"# Van ban so {doc_number}\n"):500].strip() + "..."

    with get_db() as conn:
        existing = conn.execute("SELECT id FROM documents WHERE doc_number = ?", (doc_number,)).fetchone()
        if existing: return existing["id"]

        cursor = conn.execute(
            """INSERT INTO documents 
               (doc_number, title, doc_type, issuing_date, effective_date, effectiveness_status, issuing_authority, content_markdown, summary)
               VALUES (?, ?, ?, ?, ?, 'con_hieu_luc', ?, ?, ?)""",
            (doc_number, title, doc_type, issuing_date, issuing_date, issuing_authority, content_markdown, summary),
        )
        doc_id = cursor.lastrowid

        dieu_map = {}
        for chunk in chunks:
            dieu = chunk.get("dieu")
            if dieu and dieu not in dieu_map:
                txt = clean_text(chunk.get("text", ""))
                sec_title = f"Dieu {dieu}"
                first_line = txt.split('\n')[0]
                if len(first_line) < 100 and re.match(r'^Di\u1ec1u \d+', first_line, re.I):
                    sec_title = first_line
                sec = conn.execute(
                    "INSERT INTO doc_sections (document_id, section_type, number, title, content) VALUES (?, ?, ?, ?, ?)",
                    (doc_id, 'dieu', str(dieu), sec_title, txt),
                )
                dieu_map[dieu] = sec.lastrowid

        for i, chunk in enumerate(chunks):
            section_id = dieu_map.get(chunk.get("dieu"))
            text = clean_text(chunk.get("text", ""))
            conn.execute(
                "INSERT INTO chunks (document_id, section_id, content, chunk_index, token_count, dieu, khoan, chuong) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (doc_id, section_id, text, i, chunk.get("token_count", 0), chunk.get("dieu"), chunk.get("khoan"), chunk.get("chuong")),
            )
    print(f"[OK] {doc_number} | Chunks: {len(chunks)}")
    return doc_id

INVALID_DOC_NUMBERS = {"", "N/A", "Trang chu", "Trang ch\u1ee7", "n/a", "none", "null", "Trang"}

def is_valid_doc_number(doc_number: str) -> bool:
    if not doc_number: return False
    d = str(doc_number).strip()
    return d not in INVALID_DOC_NUMBERS and len(d) >= 3 and any(c.isdigit() for c in d)

def ingest_folder(folder: str) -> int:
    json_files = glob.glob(os.path.join(folder, "*.json"))
    if not json_files: return 0
    print(f"[Ingest] Scanning {len(json_files)} files...")
    doc_groups = defaultdict(list)
    doc_hashes = defaultdict(set)
    for fp in json_files:
        try:
            with open(fp, encoding="utf-8") as f: data = json.load(f)
            fname = os.path.basename(fp)
            prefix = fname[:12] if len(fname) > 12 else fname
            for chunk in data.get("chunks", []):
                txt = clean_text(chunk.get("text", ""))
                if not txt: continue
                h = get_text_hash(txt)
                doc_num = str(chunk.get("document_number", "")).strip()
                target_key = doc_num if is_valid_doc_number(doc_num) else prefix
                if h not in doc_hashes[target_key]:
                    doc_hashes[target_key].add(h)
                    doc_groups[target_key].append(chunk)
        except Exception: pass
    print(f"[Ingest] Deduped into {len(doc_groups)} documents.")
    count = 0
    for doc_number, chunks in sorted(doc_groups.items()):
        try:
            if ingest_document(doc_number, chunks) > 0: count += 1
        except Exception as e: print(f"[ERR] {doc_number}: {e}")
    return count

def ingest_all():
    if os.path.isdir(CHUNKS_DIR): ingest_folder(CHUNKS_DIR)
    elif os.path.isdir(DATA_DIR): ingest_folder(DATA_DIR)

def seed_if_empty():
    if is_empty(): ingest_all()

if __name__ == "__main__":
    ingest_all()
