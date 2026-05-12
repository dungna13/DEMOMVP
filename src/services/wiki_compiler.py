"""
wiki_compiler.py — Phase 3: Knowledge Wiki Compilation
Áp dụng Karpathy LLM Wiki Pattern cho hệ thống văn bản pháp luật.
- Sinh file Markdown chuẩn Obsidian (YAML frontmatter + [[backlinks]])
- Rule-based fallback khi LLM không khả dụng
- Lưu metadata vào bảng wiki_pages trong DB
"""

import json
import os
import re
import logging
import unicodedata
from datetime import datetime
from typing import List, Dict, Optional, Tuple
from src.database.database import get_db
from src.config import LLM_MODEL

logger = logging.getLogger(__name__)

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
WIKI_DATA_DIR = os.path.join(BASE_DIR, "wiki_data")
VAULT_DIR = os.path.join(BASE_DIR, "wiki_vault")

# ─── Helpers ────────────────────────────────────────────────────────────────

def slugify(text: str) -> str:
    text = unicodedata.normalize("NFKD", text)
    text = text.encode("ascii", "ignore").decode("ascii")
    text = re.sub(r"[^\w\s-]", "", text.lower())
    text = re.sub(r"[\s_-]+", "-", text).strip("-")
    return text[:80]

def _call_llm_safe(messages, temperature=0.1, max_tokens=1500) -> str:
    try:
        from src.core.ai_service import _call_llm
        return _call_llm(messages, temperature=temperature, max_tokens=max_tokens)
    except Exception:
        return ""

def is_llm_available() -> bool:
    try:
        from src.core.ai_service import is_ai_available
        return is_ai_available()
    except Exception:
        return False

# ─── Rule-based fallback (không cần LLM) ────────────────────────────────────

def extract_entities_regex(content: str, doc: dict) -> Dict:
    """Trích xuất thực thể bằng regex — chạy được khi không có LLM."""
    authorities = []
    if doc.get("issuing_authority"):
        authorities.append(doc["issuing_authority"])

    # Trích thêm từ nội dung
    auth_patterns = [
        r"(Bộ\s+[\w\s]+?(?=\s+(?:ban hành|quy định|hướng dẫn|chỉ đạo)))",
        r"(Ủy ban nhân dân\s+[\w\s]+?(?=\s+(?:ban hành|quyết định)))",
        r"(Thủ tướng Chính phủ)",
        r"(Chính phủ)",
    ]
    for pat in auth_patterns:
        for m in re.finditer(pat, content[:3000], re.IGNORECASE):
            val = m.group(1).strip()
            if val and val not in authorities:
                authorities.append(val)

    signer_match = re.search(r"(?:KT\.|TM\.|Thay mặt.*?)\n+([A-ZÀÁÂÃÈÉÊÌÍÒÓÔÕÙÚĂĐ][^\n]{5,60})\n", content)
    signers = [signer_match.group(1).strip()] if signer_match else []

    return {
        "authorities": authorities[:5],
        "signers": signers,
        "dates": {
            "issuance": doc.get("issuing_date", ""),
            "effective": doc.get("effective_date", "") or doc.get("issuing_date", ""),
        }
    }

def extract_key_points_regex(chunks_data: List[dict]) -> List[str]:
    """Trích key points từ cấu trúc Điều/Khoản — không cần LLM."""
    points = []
    for chunk in chunks_data[:15]:
        content = chunk.get("content", "")
        dieu = chunk.get("dieu")
        if dieu and len(content) > 30:
            first_line = content.split("\n")[0].strip()
            if len(first_line) > 10 and not first_line.startswith("Điều"):
                points.append(f"Điều {dieu}: {first_line[:120]}")
        if len(points) >= 5:
            break
    return points

def build_summary_fallback(doc: dict, content: str) -> str:
    """Tóm tắt đơn giản từ metadata + đoạn đầu — không cần LLM."""
    authority = doc.get("issuing_authority", "Cơ quan ban hành")
    doc_number = doc.get("doc_number", "")
    issuing_date = doc.get("issuing_date", "")
    snippet = " ".join(content[:600].split())[:400]
    return (
        f"{authority} ban hành văn bản số {doc_number} ngày {issuing_date}. "
        f"Nội dung: {snippet}..."
    )

# ─── LLM-powered generation ─────────────────────────────────────────────────

def generate_summary_llm(content: str, doc_number: str) -> str:
    result = _call_llm_safe([
        {"role": "system", "content": "Bạn là chuyên gia pháp luật Việt Nam. Tóm tắt văn bản sau trong 3-5 câu, nêu rõ loại văn bản, nội dung chính và đối tượng áp dụng. Trả lời bằng tiếng Việt."},
        {"role": "user", "content": f"Văn bản {doc_number}:\n\n{content[:6000]}"},
    ], temperature=0.1)
    return result

def generate_key_points_llm(content: str) -> List[str]:
    result = _call_llm_safe([
        {"role": "system", "content": "Trích xuất 3-5 điểm quan trọng nhất của văn bản pháp luật sau. Mỗi điểm 1 dòng, bắt đầu bằng dấu '-'. Chỉ trả về danh sách."},
        {"role": "user", "content": content[:5000]},
    ], temperature=0.1)
    if result:
        return [p.lstrip("- ").strip() for p in result.split("\n") if p.strip()][:5]
    return []

def generate_qa_llm(content: str) -> List[Dict[str, str]]:
    result = _call_llm_safe([
        {"role": "system", "content": 'Sinh 3 cặp hỏi-đáp phổ biến về văn bản pháp luật. JSON: [{"question":"...","answer":"..."}]. Chỉ trả về JSON.'},
        {"role": "user", "content": content[:6000]},
    ], temperature=0.2, max_tokens=1000)
    if not result:
        return []
    try:
        s, e = result.find("["), result.rfind("]") + 1
        if s >= 0 and e > s:
            return json.loads(result[s:e])
    except Exception:
        pass
    return []

def get_legal_fields_llm(content: str) -> Tuple[List[str], float]:
    from src.core.ai_service import auto_tag
    r = auto_tag(content)
    return r.get("fields", []), r.get("confidence", 0.0)

# ─── Obsidian Markdown Generator ────────────────────────────────────────────

def build_obsidian_markdown(doc: dict, wiki_data: dict, chunks_data: List[dict]) -> str:
    """Sinh file .md chuẩn Obsidian với YAML frontmatter và [[backlinks]]."""
    doc_number = doc.get("doc_number", "")
    doc_type = doc.get("doc_type", "")
    issuing_date = doc.get("issuing_date", "")
    fields = wiki_data.get("legal_fields", [])
    tags_yaml = "\n".join([f'  - "{f}"' for f in fields]) if fields else '  - "pháp-luật"'
    sources_yaml = f'  - doc_id: {doc["id"]}\n    doc_number: "{doc_number}"\n    title: "{doc.get("title","")[:80]}"'
    key_points = wiki_data.get("key_points", [])
    qa_pairs = wiki_data.get("suggested_questions", [])
    entities = wiki_data.get("entities", {})

    # Backlinks sang các lĩnh vực liên quan
    backlinks = ""
    for field in fields[:3]:
        slug = slugify(field)
        backlinks += f"- Xem thêm: [[linh-vuc/{slug}]]\n"

    # Q&A section
    qa_section = ""
    if qa_pairs:
        qa_section = "\n## Câu hỏi thường gặp\n\n"
        for qa in qa_pairs:
            qa_section += f"**Q: {qa.get('question','')}**\n\n> {qa.get('answer','')}\n\n"

    # Key points section
    kp_section = ""
    if key_points:
        kp_section = "\n## Điểm chính\n\n"
        for kp in key_points:
            kp_section += f"- {kp}\n"

    # Entities section
    auth_str = ", ".join(entities.get("authorities", [])[:3])
    signer_str = ", ".join(entities.get("signers", [])[:2])
    dates = entities.get("dates", {})

    now = datetime.now().strftime("%Y-%m-%d")
    md = f"""---
title: "{doc.get('title','')[:100]}"
type: tom_tat
doc_number: "{doc_number}"
doc_type: "{doc_type}"
sources:
{sources_yaml}
tags:
{tags_yaml}
issuing_authority: "{doc.get('issuing_authority','')}"
issuance_date: "{issuing_date}"
effective_date: "{dates.get('effective', issuing_date)}"
created: {now}
updated: {now}
created_by_model: "{LLM_MODEL}"
reviewed: false
---

# {doc.get('title','')[:120]}

> **Số hiệu:** {doc_number} | **Ngày ban hành:** {issuing_date} | **Cơ quan:** {doc.get('issuing_authority','')}

## Tóm tắt

{wiki_data.get('summary', '_Chưa có tóm tắt._')}
{kp_section}
## Thông tin văn bản

| Thuộc tính | Giá trị |
|---|---|
| Số hiệu | {doc_number} |
| Loại văn bản | {doc_type} |
| Cơ quan ban hành | {doc.get('issuing_authority','')} |
| Ngày ban hành | {issuing_date} |
| Ngày hiệu lực | {dates.get('effective', issuing_date)} |
| Người ký | {signer_str or '_chưa xác định_'} |
| Cơ quan liên quan | {auth_str or '_chưa xác định_'} |
| Hiệu lực | {doc.get('effectiveness_status','')} |
{qa_section}
## Liên kết

{backlinks if backlinks else '- _Chưa có liên kết._'}

---
*Trang này được biên dịch tự động bởi hệ thống vào {now}. Vui lòng review trước khi sử dụng.*
"""
    return md

# ─── Vault directory helpers ─────────────────────────────────────────────────

def ensure_vault_structure():
    """Tạo cấu trúc thư mục Obsidian vault chuẩn theo HLD."""
    dirs = [
        VAULT_DIR,
        os.path.join(VAULT_DIR, "tom-tat"),
        os.path.join(VAULT_DIR, "linh-vuc"),
        os.path.join(VAULT_DIR, "chu-de"),
        os.path.join(VAULT_DIR, "khai-niem"),
        os.path.join(VAULT_DIR, "timeline"),
        os.path.join(VAULT_DIR, "templates"),
        os.path.join(VAULT_DIR, ".obsidian"),
        WIKI_DATA_DIR,
    ]
    for d in dirs:
        os.makedirs(d, exist_ok=True)

def write_vault_index(conn):
    """Sinh/cập nhật file index.md — mục lục toàn vault."""
    rows = conn.execute(
        "SELECT slug, title, page_type, doc_number, created_at FROM wiki_pages ORDER BY created_at DESC LIMIT 100"
    ).fetchall()
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    lines = [f"# Mục lục Knowledge Wiki\n\n_Cập nhật: {now}_\n\n## Danh sách văn bản đã biên dịch\n"]
    for r in rows:
        lines.append(f"- [[tom-tat/{r['slug']}|{r['title'][:80]}]] ({r['doc_number']})")
    with open(os.path.join(VAULT_DIR, "index.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

def append_log(message: str):
    """Ghi vào log.md (append-only)."""
    log_path = os.path.join(VAULT_DIR, "log.md")
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(f"\n- [{ts}] {message}")

# ─── Core compiler ────────────────────────────────────────────────────────────

def compile_wiki_for_document(doc_id: int) -> Optional[str]:
    """Biên dịch Phase 3 cho một văn bản — có LLM hoặc rule-based."""
    ensure_vault_structure()
    use_llm = is_llm_available()

    with get_db() as conn:
        doc = conn.execute("SELECT * FROM documents WHERE id = ?", (doc_id,)).fetchone()
        if not doc:
            return None
        doc = dict(doc)

        chunks_rows = conn.execute(
            "SELECT content, dieu, khoan, chunk_index FROM chunks WHERE document_id = ? ORDER BY chunk_index",
            (doc_id,)
        ).fetchall()
        chunks_data = [dict(r) for r in chunks_rows]

        content = doc.get("content_markdown") or "\n".join(c["content"] for c in chunks_data)
        doc_number = doc.get("doc_number", "")
        logger.info(f"[Wiki] Compiling doc {doc_id} ({doc_number}) — LLM={'yes' if use_llm else 'rule-based'}")

        # --- Generate wiki components ---
        if use_llm:
            summary = generate_summary_llm(content, doc_number) or build_summary_fallback(doc, content)
            key_points = generate_key_points_llm(content) or extract_key_points_regex(chunks_data)
            qa_pairs = generate_qa_llm(content)
            legal_fields, confidence = get_legal_fields_llm(content)
        else:
            summary = build_summary_fallback(doc, content)
            key_points = extract_key_points_regex(chunks_data)
            qa_pairs = []
            legal_fields = []
            confidence = 0.0

        entities = extract_entities_regex(content, doc)

        wiki_data = {
            "summary": summary,
            "key_points": key_points,
            "legal_fields": legal_fields,
            "suggested_questions": qa_pairs,
            "entities": entities,
        }

        # --- Build slug and markdown ---
        slug = slugify(f"{doc_number}-{doc.get('doc_type','')}")
        if not slug:
            slug = f"doc-{doc_id}"

        md_content = build_obsidian_markdown(doc, wiki_data, chunks_data)
        md_rel_path = os.path.join("tom-tat", f"{slug}.md")
        md_abs_path = os.path.join(VAULT_DIR, md_rel_path)

        with open(md_abs_path, "w", encoding="utf-8") as f:
            f.write(md_content)

        # --- Save JSON (backward compat with wiki_data/) ---
        safe_num = doc_number.replace("/", "_").replace("-", "_")
        json_path = os.path.join(WIKI_DATA_DIR, f"{doc_id}_{safe_num}.json")
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump({
                "source_id": f"wiki_{doc_id}",
                "document_number": doc_number,
                "title": doc.get("title", ""),
                "wiki_data": wiki_data,
                "model": LLM_MODEL,
                "processed_at": datetime.now().isoformat(),
            }, f, ensure_ascii=False, indent=2)

        # --- Upsert into wiki_pages DB ---
        existing = conn.execute("SELECT id FROM wiki_pages WHERE slug = ?", (slug,)).fetchone()
        if existing:
            conn.execute(
                """UPDATE wiki_pages SET title=?, doc_number=?, legal_fields=?, tags=?,
                   summary=?, key_points=?, suggested_qa=?, entities=?, markdown_path=?,
                   markdown_content=?, model_used=?, ai_confidence=?, updated_at=datetime('now')
                   WHERE slug=?""",
                (doc.get("title",""), doc_number, json.dumps(legal_fields, ensure_ascii=False),
                 json.dumps(legal_fields, ensure_ascii=False), summary,
                 json.dumps(key_points, ensure_ascii=False), json.dumps(qa_pairs, ensure_ascii=False),
                 json.dumps(entities, ensure_ascii=False), md_rel_path, md_content,
                 LLM_MODEL, confidence, slug)
            )
        else:
            conn.execute(
                """INSERT INTO wiki_pages (slug, title, page_type, document_id, doc_number,
                   legal_fields, tags, summary, key_points, suggested_qa, entities,
                   markdown_path, markdown_content, model_used, ai_confidence)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (slug, doc.get("title",""), "tom_tat", doc_id, doc_number,
                 json.dumps(legal_fields, ensure_ascii=False), json.dumps(legal_fields, ensure_ascii=False),
                 summary, json.dumps(key_points, ensure_ascii=False),
                 json.dumps(qa_pairs, ensure_ascii=False), json.dumps(entities, ensure_ascii=False),
                 md_rel_path, md_content, LLM_MODEL, confidence)
            )

        # Mark document as wiki_compiled
        try:
            conn.execute("UPDATE documents SET wiki_compiled=1 WHERE id=?", (doc_id,))
        except Exception:
            pass

        write_vault_index(conn)
        append_log(f"Compiled wiki for {doc_number} (doc_id={doc_id}, slug={slug})")

        return json_path


def compile_all_wiki(limit: Optional[int] = None, skip_existing: bool = True) -> int:
    """Biên dịch wiki cho toàn bộ tài liệu chưa xử lý."""
    ensure_vault_structure()
    with get_db() as conn:
        if skip_existing:
            try:
                rows = conn.execute(
                    "SELECT id FROM documents WHERE wiki_compiled = 0" + (f" LIMIT {limit}" if limit else "")
                ).fetchall()
            except Exception:
                rows = conn.execute(
                    "SELECT id FROM documents" + (f" LIMIT {limit}" if limit else "")
                ).fetchall()
        else:
            rows = conn.execute(
                "SELECT id FROM documents" + (f" LIMIT {limit}" if limit else "")
            ).fetchall()

    count = 0
    for row in rows:
        try:
            path = compile_wiki_for_document(row["id"])
            if path:
                count += 1
                print(f"[OK] {row['id']} → {os.path.basename(path)}")
        except Exception as e:
            logger.error(f"[ERR] doc {row['id']}: {e}")
    return count


# ─── Lint Service ─────────────────────────────────────────────────────────────

def lint_wiki() -> List[Dict]:
    """Kiểm tra tính nhất quán của toàn bộ wiki theo HLD §9.4."""
    issues = []
    with get_db() as conn:
        pages = conn.execute("SELECT id, slug, title, markdown_content, document_id FROM wiki_pages").fetchall()
        all_slugs = {r["slug"] for r in pages}

        for page in pages:
            page_issues = []
            content = page["markdown_content"] or ""

            # 1. Broken [[backlinks]]
            for link_match in re.finditer(r"\[\[([^\]]+)\]\]", content):
                link = link_match.group(1).split("|")[0].strip()
                # Remove subfolder prefix for slug check
                link_slug = slugify(link.replace("/", "-"))
                base_slug = link.split("/")[-1]
                if base_slug not in all_slugs and link_slug not in all_slugs:
                    page_issues.append({"type": "broken_link", "link": link})

            # 2. Văn bản hết hiệu lực được dẫn chiếu
            if page["document_id"]:
                doc = conn.execute(
                    "SELECT effectiveness_status FROM documents WHERE id=?",
                    (page["document_id"],)
                ).fetchone()
                if doc and doc["effectiveness_status"] == "het_hieu_luc":
                    page_issues.append({"type": "expired_doc", "doc_id": page["document_id"]})

            # 3. Trang mồ côi (không có backlink từ trang khác)
            is_referenced = False
            for other_page in pages:
                if other_page["slug"] == page["slug"]:
                    continue
                other_content = other_page["markdown_content"] or ""
                if page["slug"] in other_content or page["title"][:20] in other_content:
                    is_referenced = True
                    break
            if not is_referenced:
                page_issues.append({"type": "orphan_page"})

            if page_issues:
                issues.append({"page_slug": page["slug"], "title": page["title"], "issues": page_issues})
                lint_status = "warn" if all(i["type"] != "broken_link" for i in page_issues) else "error"
                conn.execute(
                    "UPDATE wiki_pages SET lint_status=?, lint_issues=? WHERE id=?",
                    (lint_status, json.dumps(page_issues, ensure_ascii=False), page["id"])
                )
            else:
                conn.execute("UPDATE wiki_pages SET lint_status='ok', lint_issues='[]' WHERE id=?", (page["id"],))

    logger.info(f"[Lint] Checked {len(pages)} pages, found {len(issues)} with issues.")
    return issues


def get_wiki_status() -> Dict:
    """Thống kê Phase 3."""
    with get_db() as conn:
        total_docs = conn.execute("SELECT COUNT(*) as n FROM documents").fetchone()["n"]
        try:
            compiled = conn.execute("SELECT COUNT(*) as n FROM documents WHERE wiki_compiled=1").fetchone()["n"]
        except Exception:
            compiled = conn.execute("SELECT COUNT(*) as n FROM wiki_pages").fetchone()["n"]
        wiki_total = conn.execute("SELECT COUNT(*) as n FROM wiki_pages").fetchone()["n"]
        reviewed = conn.execute("SELECT COUNT(*) as n FROM wiki_pages WHERE reviewed=1").fetchone()["n"]
        lint_issues = conn.execute("SELECT COUNT(*) as n FROM wiki_pages WHERE lint_status != 'ok'").fetchone()["n"]
    return {
        "total_documents": total_docs,
        "wiki_compiled": compiled,
        "wiki_pages": wiki_total,
        "reviewed": reviewed,
        "pending_review": wiki_total - reviewed,
        "lint_issues": lint_issues,
        "vault_dir": VAULT_DIR,
        "wiki_data_dir": WIKI_DATA_DIR,
    }
