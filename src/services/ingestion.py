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
from src.database.database import get_db, is_empty

CHUNKS_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "chunks"))
DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "data")

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

def parse_clean_title(text: str, doc_type: str, doc_number: str) -> str:
    # 1. Chuẩn hóa khoảng trắng và dòng
    lines = [line.strip() for line in text.split('\n') if line.strip()]
    
    # 2. Tìm các dòng chứa loại văn bản như QUYẾT ĐỊNH, NGHỊ QUYẾT, THÔNG TƯ, NGHỊ ĐỊNH, LUẬT, CHỈ THỊ
    type_keywords = ["QUYẾT ĐỊNH", "NGHỊ QUYẾT", "THÔNG TƯ", "NGHỊ ĐỊNH", "LUẬT", "CHỈ THỊ", "THÔNG BÁO", "HƯỚNG DẪN", "QUYET DINH", "NGHI QUYET", "THONG TU", "NGHI DINH", "LUAT", "CHI THI", "THONG BAO", "HUONG DAN"]
    
    for idx, line in enumerate(lines):
        line_upper = line.upper()
        for kw in type_keywords:
            if line_upper == kw or line_upper.startswith(kw + " "):
                if len(line) > len(kw) + 5:
                    title_candidate = line[len(kw):].strip()
                    title_candidate = re.sub(r'^[:\-\s\d/]+', '', title_candidate)
                    if len(title_candidate) > 10:
                        return title_candidate
                
                title_lines = []
                for j in range(idx + 1, min(idx + 5, len(lines))):
                    next_line = lines[j]
                    next_line_upper = next_line.upper()
                    if any(next_line_upper.startswith(w) for w in ["CĂN CỨ", "CAN CU", "ĐIỀU 1", "DIEU 1", "THỦ TƯỚNG", "THU TUONG", "BỘ TRƯỞNG", "BO TRUONG", "KÍNH GỬI", "KINH GUI"]):
                        break
                    if "NGƯỜI KÝ" in next_line_upper or "KÝ BỞI" in next_line_upper or "CỘNG HÒA" in next_line_upper or "ĐỘC LẬP" in next_line_upper:
                        continue
                    title_lines.append(next_line)
                
                if title_lines:
                    full_title = " ".join(title_lines).strip()
                    full_title = re.sub(r'\s+', ' ', full_title)
                    if len(full_title) > 300:
                        full_title = full_title[:297] + "..."
                    if len(full_title) > 10:
                        return full_title

    # 3. Tìm các mẫu V/v, Vlv, Về việc
    vv_patterns = [
        r'(?:V/v|Vlv|V\s*l\s*v|Về\s+việc|Ve\s+viec)[:\-\s]+(.*?)(?:\n|$)',
        r'(?:V/v|Vlv|V\s*l\s*v|Về\s+việc|Ve\s+viec)\s+(.*?)(?:\n|$)'
    ]
    for pattern in vv_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            # Lấy vị trí của pattern trong text
            pos = text.lower().find(match.group(0).lower()[:10])
            if pos != -1:
                sub_text = text[pos:]
                # Tìm tất cả các dòng tiếp theo
                sub_lines = [l.strip() for l in sub_text.split('\n') if l.strip()]
                vv_accumulated = []
                for sl in sub_lines:
                    sl_upper = sl.upper()
                    # Bỏ qua dòng chứa ngày tháng hoặc địa danh hoặc thông tin ký
                    if "NGƯỜI KÝ" in sl_upper or "KÝ BỞI" in sl_upper or "CỘNG HÒA" in sl_upper or "ĐỘC LẬP" in sl_upper or "KÍNH GỬI" in sl_upper:
                        continue
                    # Nếu dòng bắt đầu bằng địa danh ngày tháng, ví dụ "Hà Nội, ngày..."
                    if re.match(r'^[a-zA-ZĂâđêôư\s]+,\s*ngày\s+\d+', sl, re.I):
                        continue
                    # Nếu dòng có chữ V/v thì lấy phần sau chữ V/v
                    if re.match(r'^(?:V/v|Vlv|Về việc)[:\-\s]*', sl, re.I):
                        sl = re.sub(r'^(?:V/v|Vlv|Về việc)[:\-\s]*', '', sl, flags=re.I).strip()
                    # Dừng nếu gặp "Kính gửi" ở dòng độc lập
                    if sl_upper.startswith("KÍNH GỬI") or sl_upper.startswith("KINH GUI"):
                        break
                    if len(sl) > 2:
                        vv_accumulated.append(sl)
                    if len(vv_accumulated) >= 3: # Ghép tối đa 3 dòng liên quan
                        break
                if vv_accumulated:
                    full_vv = " ".join(vv_accumulated).strip()
                    full_vv = re.sub(r'\s+', ' ', full_vv)
                    # Lọc bỏ phần đuôi nếu có ngày tháng bị thừa
                    date_match = re.search(r'(?:Hà Nội|ngày\s+\d+|tháng\s+\d+)', full_vv, re.IGNORECASE)
                    if date_match and date_match.start() > 10:
                        full_vv = full_vv[:date_match.start()].strip()
                    full_vv = re.sub(r'[:\-\s,\.]+$', '', full_vv).strip()
                    if len(full_vv) > 10:
                        if not full_vv.lower().startswith("về việc"):
                            full_vv = "Về việc " + full_vv
                        return full_vv

    # 4. Fallback: tìm dòng phù hợp trong 12 dòng đầu
    valid_lines = []
    for line in lines[:12]:
        line_upper = line.upper()
        if any(w in line_upper for w in ["NGƯỜI KÝ", "KÝ BỞI", "CỘNG HÒA", "ĐỘC LẬP", "VĂN PHÒNG", "SỐ:", "HÀ NỘI,", "NGÀY THÁNG", "KÍNH GỬI"]):
            continue
        if len(line) >= 15 and len(line) <= 200:
            valid_lines.append(line)
            
    if valid_lines:
        return valid_lines[0]
        
    return ""

def build_title(doc_number: str, issuing_authority: str, chunks: list) -> str:
    doc_type = parse_doc_type(doc_number)
    type_map = {
        "quyet_dinh": "Quyết định", "nghi_dinh": "Nghị định",
        "thong_tu": "Thông tư", "luat": "Luật",
        "nghi_quyet": "Nghị quyết", "chi_thi": "Chỉ thị", "cong_van": "Công văn",
    }
    type_label = type_map.get(doc_type, "Văn bản")
    header = chunks[0] if chunks else {}
    text = clean_text(header.get("text", ""))
    
    clean_t = parse_clean_title(text, doc_type, doc_number)
    if clean_t:
        return f"{type_label} số {doc_number}: {clean_t}"
    
    return f"{type_label} số {doc_number}"

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
