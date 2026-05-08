"""
legal_relations.py — Phase 2: Trích xuất quan hệ pháp lý
Phát hiện quan hệ: thay thế, sửa đổi, hướng dẫn, bãi bỏ, viện dẫn
Kết hợp regex + LLM fallback
"""

import re
import json
import logging
from typing import List, Dict, Optional, Tuple
from src.database.database import get_db

logger = logging.getLogger(__name__)

# ─── Regex Patterns cho quan hệ pháp lý ──────────────────────────────────

RELATION_PATTERNS = {
    "thay_the": [
        r"thay\s+thế\s+(Luật|Nghị\s+định|Thông\s+tư|Quyết\s+định|Pháp\s+lệnh)\s+(số\s+)?([^\s,;\.]+)",
        r"(Luật|Nghị\s+định|Thông\s+tư|Quyết\s+định)\s+(số\s+)?([^\s,;\.]+)\s+hết\s+hiệu\s+lực",
    ],
    "sua_doi": [
        r"sửa\s+đổi[,\s]?\s*bổ\s+sung\s+(một\s+số\s+điều\s+)?(của\s+)?(Luật|Nghị\s+định|Thông\s+tư|Quyết\s+định)\s+(số\s+)?([^\s,;\.]+)",
        r"sửa\s+đổi\s+(Điều\s+\d+[,\s]*)+\s*(của\s+)?(Luật|Nghị\s+định|Thông\s+tư|Quyết\s+định)\s+(số\s+)?([^\s,;\.]+)",
    ],
    "huong_dan": [
        r"hướng\s+dẫn\s+(thi\s+hành\s+)?(một\s+số\s+điều\s+)?(của\s+)?(Luật|Nghị\s+định|Thông\s+tư|Quyết\s+định)\s+(số\s+)?([^\s,;\.]+)",
        r"quy\s+định\s+chi\s+tiết\s+(thi\s+hành\s+)?(một\s+số\s+điều\s+)?(của\s+)?(Luật|Nghị\s+định|Thông\s+tư)\s+(số\s+)?([^\s,;\.]+)",
    ],
    "bai_bo": [
        r"bãi\s+bỏ\s+(Điều\s+\d+[,\s]*)+\s*(của\s+)?(Luật|Nghị\s+định|Thông\s+tư|Quyết\s+định)\s+(số\s+)?([^\s,;\.]+)",
        r"bãi\s+bỏ\s+(Luật|Nghị\s+định|Thông\s+tư|Quyết\s+định)\s+(số\s+)?([^\s,;\.]+)",
    ],
    "vien_dan": [
        r"căn\s+cứ\s+(Luật|Nghị\s+định|Thông\s+tư|Quyết\s+định|Bộ\s+luật|Pháp\s+lệnh)\s+(số\s+)?([^\s,;]+)",
        r"theo\s+quy\s+định\s+tại\s+(Điều\s+\d+)?\s*(Luật|Nghị\s+định|Thông\s+tư|Quyết\s+định)\s+(số\s+)?([^\s,;\.]+)",
    ],
}

# Patterns để trích xuất số hiệu văn bản
DOC_NUMBER_PATTERN = re.compile(
    r'\b(\d+(?:/\d+)?(?:/[A-ZĐ\-]+)+)\b',
    re.UNICODE
)


def extract_doc_numbers_from_text(text: str) -> List[str]:
    """Trích xuất tất cả số hiệu văn bản từ text."""
    return DOC_NUMBER_PATTERN.findall(text)


def extract_relations_regex(content: str, source_doc_number: str) -> List[Dict]:
    """
    Trích xuất quan hệ pháp lý bằng regex.
    Returns: list of {relation_type, target_doc_number, source_section, confidence, detected_by}
    """
    if not content:
        return []

    relations = []
    seen = set()

    for rel_type, patterns in RELATION_PATTERNS.items():
        for pattern in patterns:
            for match in re.finditer(pattern, content, re.IGNORECASE | re.UNICODE):
                matched_text = match.group(0)
                # Trích xuất số hiệu từ matched text
                doc_numbers = extract_doc_numbers_from_text(matched_text)
                for doc_num in doc_numbers:
                    if doc_num != source_doc_number:
                        key = (rel_type, doc_num)
                        if key not in seen:
                            seen.add(key)
                            # Tìm section context
                            source_section = _find_section_context(content, match.start())
                            relations.append({
                                "relation_type": rel_type,
                                "target_doc_number": doc_num,
                                "source_section": source_section,
                                "target_section": "",
                                "confidence": 1.0,
                                "detected_by": "regex",
                                "matched_text": matched_text[:200],
                            })

    logger.info(f"[Relations] Regex found {len(relations)} relations for {source_doc_number}")
    return relations


def _find_section_context(content: str, position: int) -> str:
    """Tìm Điều/Khoản chứa vị trí position."""
    # Tìm ngược lên để tìm "Điều X" gần nhất
    before = content[:position]
    match = re.search(r'Điều\s+(\d+)', before[::-1][:500][::-1], re.IGNORECASE)
    if match:
        return f"Điều {match.group(1)}"
    return ""


def extract_relations_llm(content: str, source_doc_number: str) -> List[Dict]:
    """
    Trích xuất quan hệ pháp lý bằng LLM (cho trường hợp phức tạp).
    Fallback khi regex không đủ.
    """
    from src.core.ai_service import _call_llm, is_ai_available

    if not is_ai_available():
        return []

    truncated = content[:6000]

    messages = [
        {"role": "system", "content": """Phân tích văn bản pháp luật Việt Nam sau và trích xuất các quan hệ pháp lý.

Trả về JSON array (chỉ JSON, không giải thích):
[
  {
    "relation_type": "thay_the|sua_doi|huong_dan|bai_bo|vien_dan",
    "target_doc_number": "số hiệu văn bản đích",
    "source_section": "Điều/Khoản nguồn (nếu có)",
    "target_section": "Điều/Khoản đích (nếu có)",
    "confidence": 0.XX
  }
]

Chỉ trích xuất quan hệ RÕ RÀNG, không suy đoán. Nếu không có quan hệ nào, trả về []."""},
        {"role": "user", "content": f"Văn bản {source_doc_number}:\n\n{truncated}"},
    ]

    result = _call_llm(messages, temperature=0.0, max_tokens=1000)
    if not result:
        return []

    try:
        json_start = result.find("[")
        json_end = result.rfind("]") + 1
        if json_start >= 0 and json_end > json_start:
            parsed = json.loads(result[json_start:json_end])
            for item in parsed:
                item["detected_by"] = "llm"
            return parsed
    except (json.JSONDecodeError, ValueError) as e:
        logger.warning(f"[Relations] Failed to parse LLM response: {e}")

    return []


def extract_and_store_relations(doc_id: int) -> int:
    """
    Trích xuất quan hệ pháp lý cho 1 văn bản và lưu vào DB.
    Returns: số quan hệ tìm được.
    """
    with get_db() as conn:
        doc = conn.execute(
            "SELECT id, doc_number, content_markdown FROM documents WHERE id = ?",
            (doc_id,)
        ).fetchone()
        if not doc:
            return 0

        doc = dict(doc)
        content = doc.get("content_markdown", "")
        doc_number = doc.get("doc_number", "")

        # Regex extraction
        relations = extract_relations_regex(content, doc_number)

        # LLM extraction (bổ sung cho regex)
        llm_relations = []
        try:
            llm_relations = extract_relations_llm(content, doc_number)
        except Exception as e:
            logger.warning(f"[Relations] LLM extraction failed for doc {doc_id}: {e}")

        # Chỉ thêm quan hệ chưa được regex phát hiện
        existing_targets = {(r["relation_type"], r["target_doc_number"]) for r in relations}
        for lr in llm_relations:
            key = (lr.get("relation_type", ""), lr.get("target_doc_number", ""))
            if key not in existing_targets and lr.get("target_doc_number"):
                relations.append(lr)

        # Lưu vào DB
        count = 0
        for rel in relations:
            target_doc_num = rel.get("target_doc_number", "")
            if not target_doc_num:
                continue

            # Tìm target_doc_id
            target = conn.execute(
                "SELECT id FROM documents WHERE doc_number = ?",
                (target_doc_num,)
            ).fetchone()
            target_doc_id = target["id"] if target else None

            # Check duplicate
            existing = conn.execute(
                """SELECT id FROM doc_relations 
                   WHERE source_doc_id = ? AND target_doc_number = ? AND relation_type = ?""",
                (doc_id, target_doc_num, rel["relation_type"])
            ).fetchone()

            if not existing:
                conn.execute(
                    """INSERT INTO doc_relations 
                       (source_doc_id, target_doc_id, target_doc_number, relation_type,
                        source_section, target_section, detected_by, confidence)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                    (doc_id, target_doc_id, target_doc_num, rel["relation_type"],
                     rel.get("source_section", ""), rel.get("target_section", ""),
                     rel.get("detected_by", "regex"), rel.get("confidence", 1.0))
                )
                count += 1
        
        # Đánh dấu đã xử lý
        conn.execute("UPDATE documents SET relations_extracted = 1 WHERE id = ?", (doc_id,))

    logger.info(f"[Relations] Stored {count} relations for doc {doc_id} ({doc_number})")
    return count


def get_document_relations(doc_id: int) -> Dict:
    """Lấy tất cả quan hệ pháp lý của 1 văn bản."""
    from src.config import RELATION_TYPES

    with get_db() as conn:
        # Quan hệ xuất phát từ văn bản này
        outgoing = conn.execute(
            """SELECT r.*, d.title as target_title, d.doc_type as target_doc_type,
                      d.effectiveness_status as target_effectiveness
               FROM doc_relations r
               LEFT JOIN documents d ON r.target_doc_id = d.id
               WHERE r.source_doc_id = ?
               ORDER BY r.relation_type""",
            (doc_id,)
        ).fetchall()

        # Quan hệ trỏ đến văn bản này
        incoming = conn.execute(
            """SELECT r.*, d.title as source_title, d.doc_number as source_doc_number,
                      d.doc_type as source_doc_type
               FROM doc_relations r
               LEFT JOIN documents d ON r.source_doc_id = d.id
               WHERE r.target_doc_id = ?
               ORDER BY r.relation_type""",
            (doc_id,)
        ).fetchall()

        return {
            "outgoing": [dict(r) for r in outgoing],
            "incoming": [dict(r) for r in incoming],
            "relation_labels": RELATION_TYPES,
        }


def extract_all_relations(max_workers: int = 2) -> int:
    """Trích xuất quan hệ cho tất cả văn bản chưa được xử lý (đa luồng)."""
    from concurrent.futures import ThreadPoolExecutor

    with get_db() as conn:
        # Chỉ lấy các document chưa được xử lý relations
        doc_ids = conn.execute(
            "SELECT id FROM documents WHERE relations_extracted = 0"
        ).fetchall()

    if not doc_ids:
        logger.info("[Relations] All documents already processed.")
        return 0

    logger.info(f"[Relations] Starting extraction for {len(doc_ids)} documents with {max_workers} workers...")
    
    total = 0
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        results = list(executor.map(extract_and_store_relations, [row["id"] for row in doc_ids]))
        total = sum(results)

    logger.info(f"[Relations] Finished. Total: {total} relations extracted for {len(doc_ids)} documents")
    return total
