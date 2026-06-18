"""
ingestion_graph.py — Phase 5: LangGraph StateGraph cho Upload & OCR Pipeline
Điều phối toàn bộ quy trình: Validate → OCR/DOCX → Parse → DB → Vector → Relations → Wiki
"""

import os
import io
import json
import hashlib
import logging
import uuid
from datetime import datetime
from typing import TypedDict, List, Dict, Optional

from langgraph.graph import StateGraph, END

logger = logging.getLogger(__name__)

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
CHUNKS_UPLOADS_DIR = os.path.join(BASE_DIR, "chunks", "uploads")
os.makedirs(CHUNKS_UPLOADS_DIR, exist_ok=True)


# ═══════════════════════════════════════════════════════════════════════════════
#  STATE DEFINITION
# ═══════════════════════════════════════════════════════════════════════════════

class IngestionState(TypedDict, total=False):
    # ── Input ──
    file_bytes: bytes
    file_name: str
    file_type: str               # "pdf" | "docx"
    file_hash: str               # SHA-256

    # ── OCR Output ──
    ocr_text: str
    ocr_success: bool

    # ── Parse Output ──
    doc_metadata: Dict
    chunks: List[Dict]

    # ── Pipeline Result ──
    document_id: Optional[int]
    vector_count: int
    relations_count: int
    wiki_slug: Optional[str]

    # ── Tracking ──
    status: str
    current_node: str
    error_message: Optional[str]


# ═══════════════════════════════════════════════════════════════════════════════
#  NODE FUNCTIONS
# ═══════════════════════════════════════════════════════════════════════════════

def validate_upload_node(state: IngestionState) -> IngestionState:
    """Node 1: Kiểm tra định dạng file và tính SHA-256 để phát hiện trùng lặp."""
    state["current_node"] = "validate_upload"
    state["status"] = "validating"

    file_name = state.get("file_name", "")
    file_bytes = state.get("file_bytes", b"")

    # Kiểm tra định dạng
    ext = os.path.splitext(file_name)[1].lower()
    if ext not in (".pdf", ".docx"):
        state["status"] = "failed"
        state["error_message"] = f"Định dạng không hỗ trợ: {ext}. Chỉ chấp nhận .pdf và .docx"
        return state

    state["file_type"] = "pdf" if ext == ".pdf" else "docx"

    # Tính SHA-256
    file_hash = hashlib.sha256(file_bytes).hexdigest()
    state["file_hash"] = file_hash

    # Kiểm tra trùng lặp trong DB
    try:
        from src.database.database import get_db
        with get_db() as conn:
            existing = conn.execute(
                "SELECT id, doc_number, title FROM documents WHERE file_hash = ?",
                (file_hash,)
            ).fetchone()
            if existing:
                state["status"] = "duplicate"
                state["document_id"] = existing["id"]
                state["error_message"] = (
                    f"File đã tồn tại trong hệ thống. "
                    f"Document ID: {existing['id']}, Số hiệu: {existing['doc_number']}"
                )
                return state
    except Exception as e:
        logger.warning(f"[Ingest] Không thể kiểm tra trùng lặp: {e}")

    logger.info(f"[Ingest] File hợp lệ: {file_name} ({state['file_type']}, hash={file_hash[:16]}...)")
    return state


def trigger_ocr_node(state: IngestionState) -> IngestionState:
    """Node 2a: Gọi OCR service bên ngoài cho file PDF."""
    state["current_node"] = "trigger_ocr"
    state["status"] = "ocr_running"

    try:
        from src.services.ocr_connector import get_ocr_connector
        connector = get_ocr_connector()
        result = connector.extract_text(
            file_bytes=state.get("file_bytes", b""),
            file_name=state.get("file_name", "")
        )
        state["ocr_success"] = result.get("success", False)
        state["ocr_text"] = result.get("text", "")

        if not state["ocr_success"]:
            state["status"] = "failed"
            state["error_message"] = f"OCR thất bại: {result.get('error', 'Không rõ lỗi')}"
            logger.error(f"[Ingest] OCR failed: {result.get('error')}")
        else:
            # Nếu OCR trả về metadata, lưu vào state
            ocr_metadata = result.get("metadata", {})
            if ocr_metadata:
                state["doc_metadata"] = ocr_metadata
            logger.info(f"[Ingest] OCR thành công, text length: {len(state['ocr_text'])}")

    except Exception as e:
        state["ocr_success"] = False
        state["status"] = "failed"
        state["error_message"] = f"OCR exception: {str(e)}"
        logger.error(f"[Ingest] OCR exception: {e}")

    return state


def extract_docx_text_node(state: IngestionState) -> IngestionState:
    """Node 2b: Đọc trực tiếp text từ file DOCX bằng python-docx (không cần OCR)."""
    state["current_node"] = "extract_docx_text"
    state["status"] = "ocr_running"

    try:
        from docx import Document
        doc = Document(io.BytesIO(state.get("file_bytes", b"")))

        # Trích xuất toàn bộ paragraphs
        paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]
        full_text = "\n".join(paragraphs)

        if not full_text.strip():
            state["ocr_success"] = False
            state["status"] = "failed"
            state["error_message"] = "File DOCX không chứa nội dung text."
            return state

        state["ocr_text"] = full_text
        state["ocr_success"] = True
        logger.info(f"[Ingest] DOCX extracted, text length: {len(full_text)}")

    except ImportError:
        state["ocr_success"] = False
        state["status"] = "failed"
        state["error_message"] = "Thư viện python-docx chưa được cài đặt."
    except Exception as e:
        state["ocr_success"] = False
        state["status"] = "failed"
        state["error_message"] = f"Lỗi đọc DOCX: {str(e)}"
        logger.error(f"[Ingest] DOCX extract error: {e}")

    return state


def parse_and_chunk_node(state: IngestionState) -> IngestionState:
    """Node 3: Bóc tách cấu trúc văn bản và chia thành chunks."""
    state["current_node"] = "parse_and_chunk"
    state["status"] = "parsing"

    ocr_text = state.get("ocr_text", "")
    if not ocr_text.strip():
        state["status"] = "failed"
        state["error_message"] = "Không có nội dung text để phân tích."
        return state

    try:
        from src.services.ingestion import (
            parse_doc_type, clean_text, parse_clean_title, get_text_hash
        )

        # Bóc tách metadata cơ bản từ text
        lines = [l.strip() for l in ocr_text.split("\n") if l.strip()]

        # Trích xuất số hiệu văn bản
        doc_number = ""
        existing_metadata = state.get("doc_metadata", {})
        if existing_metadata.get("doc_number"):
            doc_number = existing_metadata["doc_number"]
        else:
            import re
            # Tìm pattern số hiệu: XX/YYYY/XX-XX
            for line in lines[:20]:
                match = re.search(r'(\d+/\d{4}/[A-ZĐ\-]+(?:/[A-ZĐ\-]+)*)', line)
                if match:
                    doc_number = match.group(1)
                    break
                # Pattern: Số: XX/XX
                match2 = re.search(r'Số[:\s]+(\S+)', line, re.IGNORECASE)
                if match2:
                    doc_number = match2.group(1).strip(".,;:")
                    break

        if not doc_number:
            doc_number = f"UPLOAD_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

        doc_type = parse_doc_type(doc_number)
        title = parse_clean_title(ocr_text, doc_type, doc_number)
        if not title:
            title = f"Văn bản {doc_number}"

        # Chia chunks dựa trên cấu trúc Điều/Khoản
        import re
        chunks = []
        # Chia theo Điều
        dieu_pattern = re.compile(r'(Điều\s+(\d+)[\.\:]?\s*(.*))', re.IGNORECASE)
        sections = re.split(r'(?=Điều\s+\d+)', ocr_text)

        for idx, section in enumerate(sections):
            section_clean = clean_text(section)
            if not section_clean or len(section_clean) < 10:
                continue

            dieu_match = dieu_pattern.match(section_clean)
            dieu_num = None
            if dieu_match:
                dieu_num = int(dieu_match.group(2))

            # Chia thêm theo Khoản nếu có
            khoan_parts = re.split(r'(?=\d+\.\s)', section_clean)
            if len(khoan_parts) > 1 and dieu_num:
                for k_idx, kpart in enumerate(khoan_parts):
                    kpart_clean = clean_text(kpart)
                    if not kpart_clean or len(kpart_clean) < 10:
                        continue
                    khoan_match = re.match(r'^(\d+)\.\s', kpart_clean)
                    khoan_num = int(khoan_match.group(1)) if khoan_match else None
                    chunks.append({
                        "text": kpart_clean,
                        "index": len(chunks),
                        "dieu": dieu_num,
                        "khoan": khoan_num,
                        "chuong": None,
                        "document_number": doc_number,
                        "token_count": len(kpart_clean.split()),
                    })
            else:
                chunks.append({
                    "text": section_clean,
                    "index": len(chunks),
                    "dieu": dieu_num,
                    "khoan": None,
                    "chuong": None,
                    "document_number": doc_number,
                    "token_count": len(section_clean.split()),
                })

        # Nếu không tìm thấy cấu trúc Điều, chia đều theo đoạn
        if not chunks:
            chunk_size = 500  # words
            words = ocr_text.split()
            for i in range(0, len(words), chunk_size):
                chunk_text = " ".join(words[i:i + chunk_size])
                chunks.append({
                    "text": chunk_text,
                    "index": len(chunks),
                    "dieu": None,
                    "khoan": None,
                    "chuong": None,
                    "document_number": doc_number,
                    "token_count": len(chunk_text.split()),
                })

        # Cập nhật state
        state["doc_metadata"] = {
            "doc_number": doc_number,
            "title": title,
            "doc_type": doc_type,
            "issuing_date": existing_metadata.get("issuing_date", ""),
            "issuing_authority": existing_metadata.get("issuing_authority", ""),
        }
        state["chunks"] = chunks

        # Lưu JSON vào chunks/uploads/
        safe_num = doc_number.replace("/", "_").replace("-", "_")
        json_path = os.path.join(CHUNKS_UPLOADS_DIR, f"{safe_num}.json")
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump({
                "source": "upload",
                "file_name": state.get("file_name", ""),
                "file_hash": state.get("file_hash", ""),
                "processed_at": datetime.now().isoformat(),
                "chunks": chunks,
            }, f, ensure_ascii=False, indent=2)

        logger.info(f"[Ingest] Parsed {len(chunks)} chunks for {doc_number}, saved to {json_path}")

    except Exception as e:
        state["status"] = "failed"
        state["error_message"] = f"Lỗi parse_and_chunk: {str(e)}"
        logger.error(f"[Ingest] parse_and_chunk error: {e}")

    return state


def db_ingest_node(state: IngestionState) -> IngestionState:
    """Node 4: Insert vào SQLite (documents, doc_sections, chunks)."""
    state["current_node"] = "db_ingest"
    state["status"] = "ingesting"

    try:
        from src.services.ingestion import ingest_document
        metadata = state.get("doc_metadata", {})
        chunks = state.get("chunks", [])

        if not chunks:
            state["status"] = "failed"
            state["error_message"] = "Không có chunks để nạp vào database."
            return state

        doc_id = ingest_document(metadata["doc_number"], chunks)

        if doc_id > 0:
            state["document_id"] = doc_id

            # Cập nhật file_hash vào bảng documents
            from src.database.database import get_db
            with get_db() as conn:
                conn.execute(
                    "UPDATE documents SET file_hash = ? WHERE id = ?",
                    (state.get("file_hash", ""), doc_id)
                )

            logger.info(f"[Ingest] DB insert OK: document_id={doc_id}")
        else:
            state["status"] = "failed"
            state["error_message"] = f"ingest_document trả về doc_id={doc_id}"

    except Exception as e:
        state["status"] = "failed"
        state["error_message"] = f"Lỗi db_ingest: {str(e)}"
        logger.error(f"[Ingest] db_ingest error: {e}")

    return state


def vector_index_node(state: IngestionState) -> IngestionState:
    """Node 5: Sinh embedding và nạp vào Qdrant Vector DB."""
    state["current_node"] = "vector_index"
    state["status"] = "indexing"

    doc_id = state.get("document_id")
    if not doc_id:
        logger.warning("[Ingest] Bỏ qua vector_index: không có document_id")
        state["vector_count"] = 0
        return state

    try:
        from src.core.embedding_service import index_document_chunks
        count = index_document_chunks(doc_id)
        state["vector_count"] = count
        logger.info(f"[Ingest] Vector index: {count} chunks for doc_id={doc_id}")
    except ImportError:
        logger.warning("[Ingest] embedding_service không khả dụng, bỏ qua vector index")
        state["vector_count"] = 0
    except Exception as e:
        logger.warning(f"[Ingest] Vector index failed (non-critical): {e}")
        state["vector_count"] = 0

    return state


def extract_relations_node(state: IngestionState) -> IngestionState:
    """Node 6: Phát hiện quan hệ pháp lý với các văn bản hiện có."""
    state["current_node"] = "extract_relations"
    state["status"] = "extracting"

    doc_id = state.get("document_id")
    if not doc_id:
        state["relations_count"] = 0
        return state

    try:
        from src.services.legal_relations import extract_relations_for_document
        count = extract_relations_for_document(doc_id)
        state["relations_count"] = count
        logger.info(f"[Ingest] Relations: {count} for doc_id={doc_id}")
    except ImportError:
        logger.warning("[Ingest] legal_relations không khả dụng, bỏ qua")
        state["relations_count"] = 0
    except Exception as e:
        logger.warning(f"[Ingest] Relations extraction failed (non-critical): {e}")
        state["relations_count"] = 0

    return state


def compile_wiki_node(state: IngestionState) -> IngestionState:
    """Node 7: Biên soạn trang Wiki trong Obsidian Vault."""
    state["current_node"] = "compile_wiki"
    state["status"] = "compiling"

    doc_id = state.get("document_id")
    if not doc_id:
        state["wiki_slug"] = None
        state["status"] = "done"
        return state

    try:
        from src.services.wiki_compiler import compile_wiki_for_document, slugify
        path = compile_wiki_for_document(doc_id)
        if path:
            metadata = state.get("doc_metadata", {})
            doc_number = metadata.get("doc_number", "")
            doc_type = metadata.get("doc_type", "")
            state["wiki_slug"] = slugify(f"{doc_number}-{doc_type}")
            logger.info(f"[Ingest] Wiki compiled: {path}")
        else:
            state["wiki_slug"] = None
    except ImportError:
        logger.warning("[Ingest] wiki_compiler không khả dụng, bỏ qua")
        state["wiki_slug"] = None
    except Exception as e:
        logger.warning(f"[Ingest] Wiki compile failed (non-critical): {e}")
        state["wiki_slug"] = None

    state["status"] = "done"

    # Giải phóng file_bytes khỏi bộ nhớ
    state["file_bytes"] = b""

    return state


# ═══════════════════════════════════════════════════════════════════════════════
#  CONDITIONAL EDGES
# ═══════════════════════════════════════════════════════════════════════════════

def _after_validate(state: IngestionState) -> str:
    """Conditional edge sau validate: duplicate/failed → END, còn lại → phân loại file."""
    if state.get("status") in ("duplicate", "failed"):
        return "end"
    if state.get("file_type") == "docx":
        return "extract_docx"
    return "trigger_ocr"


def _after_ocr(state: IngestionState) -> str:
    """Conditional edge sau OCR/DOCX: thành công → parse, thất bại → END."""
    if state.get("ocr_success"):
        return "parse"
    return "end"


def _after_parse(state: IngestionState) -> str:
    """Conditional edge sau parse: có chunks → db_ingest, không → END."""
    if state.get("chunks") and state.get("status") != "failed":
        return "db_ingest"
    return "end"


# ═══════════════════════════════════════════════════════════════════════════════
#  BUILD GRAPH
# ═══════════════════════════════════════════════════════════════════════════════

def _build_ingestion_graph() -> StateGraph:
    """Xây dựng LangGraph StateGraph cho pipeline Ingestion."""
    graph = StateGraph(IngestionState)

    # Đăng ký nodes
    graph.add_node("validate", validate_upload_node)
    graph.add_node("trigger_ocr", trigger_ocr_node)
    graph.add_node("extract_docx", extract_docx_text_node)
    graph.add_node("parse", parse_and_chunk_node)
    graph.add_node("db_ingest", db_ingest_node)
    graph.add_node("vector_index", vector_index_node)
    graph.add_node("extract_relations", extract_relations_node)
    graph.add_node("compile_wiki", compile_wiki_node)

    # Entry point
    graph.set_entry_point("validate")

    # Conditional edges
    graph.add_conditional_edges("validate", _after_validate, {
        "trigger_ocr": "trigger_ocr",
        "extract_docx": "extract_docx",
        "end": END,
    })

    graph.add_conditional_edges("trigger_ocr", _after_ocr, {
        "parse": "parse",
        "end": END,
    })

    graph.add_conditional_edges("extract_docx", _after_ocr, {
        "parse": "parse",
        "end": END,
    })

    graph.add_conditional_edges("parse", _after_parse, {
        "db_ingest": "db_ingest",
        "end": END,
    })

    # Sequential edges: db_ingest → vector → relations → wiki → END
    graph.add_edge("db_ingest", "vector_index")
    graph.add_edge("vector_index", "extract_relations")
    graph.add_edge("extract_relations", "compile_wiki")
    graph.add_edge("compile_wiki", END)

    return graph.compile()


# ═══════════════════════════════════════════════════════════════════════════════
#  PUBLIC API
# ═══════════════════════════════════════════════════════════════════════════════

_ingestion_app = None


def _get_ingestion_app():
    global _ingestion_app
    if _ingestion_app is None:
        _ingestion_app = _build_ingestion_graph()
    return _ingestion_app


def run_ingestion_pipeline(file_bytes: bytes, file_name: str) -> dict:
    """
    Chạy pipeline ingestion đồng bộ.

    Args:
        file_bytes: Nội dung file (PDF/DOCX)
        file_name:  Tên file gốc

    Returns:
        dict: Kết quả cuối cùng của pipeline
    """
    app = _get_ingestion_app()
    initial_state: IngestionState = {
        "file_bytes": file_bytes,
        "file_name": file_name,
        "status": "pending",
        "current_node": "",
    }

    final_state = app.invoke(initial_state)

    # Cleanup: không trả về file_bytes trong response
    result = {k: v for k, v in final_state.items() if k != "file_bytes"}
    return result
