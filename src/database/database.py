"""
database.py — SQLite + FTS5 setup cho Phase 1 + Phase 2 + Phase 3 + Phase 4
Schema theo HLD: documents, doc_sections, chunks, doc_relations, doc_legal_fields + FTS5
"""

import sqlite3
import os
from contextlib import contextmanager

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "vanban.db")


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


@contextmanager
def get_db():
    conn = get_connection()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


SCHEMA_SQL = """
-- ========== BẢNG CHÍNH ==========

CREATE TABLE IF NOT EXISTS documents (
    id                   INTEGER PRIMARY KEY AUTOINCREMENT,
    doc_number           TEXT NOT NULL,
    title                TEXT NOT NULL,
    doc_type             TEXT DEFAULT 'quyet_dinh',
    issuing_date         TEXT,
    effective_date       TEXT,
    expiry_date          TEXT,
    effectiveness_status TEXT DEFAULT 'con_hieu_luc',
    gazette_number       TEXT,
    signer               TEXT,
    file_hash            TEXT,
    content_markdown     TEXT,
    structure_json       TEXT,
    summary              TEXT,
    summary_model        TEXT,
    source_url           TEXT,
    issuing_authority    TEXT,
    relations_extracted  INTEGER DEFAULT 0,  -- Flag for Phase 2
    embedding_indexed    INTEGER DEFAULT 0,  -- Flag for Vector Search
    created_at           TEXT DEFAULT (datetime('now')),
    updated_at           TEXT DEFAULT (datetime('now'))
);

-- ========== PHÂN CẤP PHÁP LÝ ==========

CREATE TABLE IF NOT EXISTS doc_sections (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    document_id    INTEGER NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    parent_id      INTEGER REFERENCES doc_sections(id),
    section_type   TEXT NOT NULL,   -- phan, chuong, muc, tieu_muc, dieu, khoan, diem
    number         TEXT,
    title          TEXT,
    content        TEXT,
    position_start INTEGER,
    position_end   INTEGER
);

-- ========== CHUNKS CHO RAG ==========

CREATE TABLE IF NOT EXISTS chunks (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    document_id  INTEGER NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    section_id   INTEGER REFERENCES doc_sections(id),
    content      TEXT NOT NULL,
    chunk_index  INTEGER,
    token_count  INTEGER,
    embedding_id TEXT,
    dieu         INTEGER,
    khoan        INTEGER,
    chuong       INTEGER
);

-- ========== PHASE 2: QUAN HỆ PHÁP LÝ ==========

CREATE TABLE IF NOT EXISTS doc_relations (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    source_doc_id    INTEGER NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    target_doc_id    INTEGER REFERENCES documents(id),
    target_doc_number TEXT,
    relation_type    TEXT NOT NULL,  -- thay_the, sua_doi, huong_dan, bai_bo, vien_dan, dinh_chinh
    source_section   TEXT,
    target_section   TEXT,
    detected_by      TEXT DEFAULT 'regex',  -- regex / llm / manual
    confidence       REAL DEFAULT 1.0,
    created_at       TEXT DEFAULT (datetime('now'))
);

-- ========== PHASE 2: LĨNH VỰC PHÁP LÝ ==========

CREATE TABLE IF NOT EXISTS doc_legal_fields (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    document_id  INTEGER NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    field_name   TEXT NOT NULL,
    confidence   REAL DEFAULT 1.0,
    source       TEXT DEFAULT 'auto',  -- auto / manual
    model        TEXT,
    created_at   TEXT DEFAULT (datetime('now'))
);

-- ========== INDEXES ==========

CREATE INDEX IF NOT EXISTS idx_docs_number          ON documents(doc_number);
CREATE INDEX IF NOT EXISTS idx_docs_type            ON documents(doc_type);
CREATE INDEX IF NOT EXISTS idx_docs_effectiveness   ON documents(effectiveness_status);
CREATE INDEX IF NOT EXISTS idx_docs_effective_date  ON documents(issuing_date);
CREATE INDEX IF NOT EXISTS idx_docs_hash            ON documents(file_hash);
CREATE INDEX IF NOT EXISTS idx_sections_doc_type    ON doc_sections(document_id, section_type);
CREATE INDEX IF NOT EXISTS idx_chunks_doc           ON chunks(document_id);
CREATE INDEX IF NOT EXISTS idx_relations_source     ON doc_relations(source_doc_id);
CREATE INDEX IF NOT EXISTS idx_relations_target     ON doc_relations(target_doc_id);
CREATE INDEX IF NOT EXISTS idx_relations_type       ON doc_relations(relation_type);
CREATE INDEX IF NOT EXISTS idx_legal_fields_doc     ON doc_legal_fields(document_id);
CREATE INDEX IF NOT EXISTS idx_legal_fields_name    ON doc_legal_fields(field_name);

-- ========== FTS5 FULL-TEXT SEARCH ==========
-- Simulate BM25 — SQLite FTS5 dùng BM25 ranking mặc định

CREATE VIRTUAL TABLE IF NOT EXISTS documents_fts USING fts5(
    doc_number,
    title,
    content_markdown,
    summary,
    issuing_authority,
    content='documents',
    content_rowid='id',
    tokenize='unicode61'
);

CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(
    content,
    content='chunks',
    content_rowid='id',
    tokenize='unicode61'
);

-- Triggers để FTS tự sync khi insert/update/delete documents
CREATE TRIGGER IF NOT EXISTS docs_ai AFTER INSERT ON documents BEGIN
    INSERT INTO documents_fts(rowid, doc_number, title, content_markdown, summary, issuing_authority)
    VALUES (new.id, new.doc_number, new.title, new.content_markdown, new.summary, new.issuing_authority);
END;

CREATE TRIGGER IF NOT EXISTS docs_ad AFTER DELETE ON documents BEGIN
    INSERT INTO documents_fts(documents_fts, rowid, doc_number, title, content_markdown, summary, issuing_authority)
    VALUES ('delete', old.id, old.doc_number, old.title, old.content_markdown, old.summary, old.issuing_authority);
END;

CREATE TRIGGER IF NOT EXISTS docs_au AFTER UPDATE ON documents BEGIN
    INSERT INTO documents_fts(documents_fts, rowid, doc_number, title, content_markdown, summary, issuing_authority)
    VALUES ('delete', old.id, old.doc_number, old.title, old.content_markdown, old.summary, old.issuing_authority);
    INSERT INTO documents_fts(rowid, doc_number, title, content_markdown, summary, issuing_authority)
    VALUES (new.id, new.doc_number, new.title, new.content_markdown, new.summary, new.issuing_authority);
END;

-- Triggers chunks FTS
CREATE TRIGGER IF NOT EXISTS chunks_ai AFTER INSERT ON chunks BEGIN
    INSERT INTO chunks_fts(rowid, content) VALUES (new.id, new.content);
END;

CREATE TRIGGER IF NOT EXISTS chunks_ad AFTER DELETE ON chunks BEGIN
    INSERT INTO chunks_fts(chunks_fts, rowid, content) VALUES ('delete', old.id, old.content);
END;

CREATE TRIGGER IF NOT EXISTS chunks_au AFTER UPDATE ON chunks BEGIN
    INSERT INTO chunks_fts(chunks_fts, rowid, content) VALUES ('delete', old.id, old.content);
    INSERT INTO chunks_fts(rowid, content) VALUES (new.id, new.content);
END;

-- ========== PHASE 3: KNOWLEDGE WIKI ==========

CREATE TABLE IF NOT EXISTS wiki_pages (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    slug             TEXT NOT NULL UNIQUE,
    title            TEXT NOT NULL,
    page_type        TEXT NOT NULL DEFAULT 'tom_tat',
    document_id      INTEGER REFERENCES documents(id) ON DELETE SET NULL,
    doc_number       TEXT,
    legal_fields     TEXT,
    tags             TEXT,
    summary          TEXT,
    key_points       TEXT,
    suggested_qa     TEXT,
    entities         TEXT,
    markdown_path    TEXT,
    markdown_content TEXT,
    model_used       TEXT,
    ai_confidence    REAL DEFAULT 0.0,
    reviewed         INTEGER DEFAULT 0,
    reviewer         TEXT,
    lint_status      TEXT DEFAULT 'ok',
    lint_issues      TEXT,
    created_at       TEXT DEFAULT (datetime('now')),
    updated_at       TEXT DEFAULT (datetime('now'))
);

-- ========== PHASE 4: CHAT HISTORY & LONG-TERM MEMORY ==========

CREATE TABLE IF NOT EXISTS chat_sessions (
    session_id  TEXT PRIMARY KEY,
    user_id     TEXT NOT NULL,
    created_at  TEXT DEFAULT (datetime('now')),
    updated_at  TEXT DEFAULT (datetime('now')),
    summary     TEXT
);

CREATE TABLE IF NOT EXISTS chat_messages (
    message_id  TEXT PRIMARY KEY,
    session_id  TEXT NOT NULL REFERENCES chat_sessions(session_id) ON DELETE CASCADE,
    role        TEXT CHECK(role IN ('user', 'assistant', 'system')),
    content     TEXT NOT NULL,
    timestamp   TEXT DEFAULT (datetime('now')),
    tokens_used INTEGER
);

-- ========== PHASE 4: LEGAL HIERARCHY & RELATIONS ==========
CREATE TABLE IF NOT EXISTS document_types (
    type_code TEXT PRIMARY KEY,
    type_name TEXT NOT NULL,
    hierarchy_rank INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS document_relations (
    relation_id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_doc_id TEXT NOT NULL,
    target_doc_id TEXT NOT NULL,
    relation_type TEXT CHECK(relation_type IN ('CAN_CU', 'HUONG_DAN', 'SUA_DOI_BO_SUNG', 'THAY_THE')),
    description TEXT
);

CREATE INDEX IF NOT EXISTS idx_wiki_slug     ON wiki_pages(slug);
CREATE INDEX IF NOT EXISTS idx_wiki_type     ON wiki_pages(page_type);
CREATE INDEX IF NOT EXISTS idx_wiki_doc_id   ON wiki_pages(document_id);
CREATE INDEX IF NOT EXISTS idx_wiki_reviewed ON wiki_pages(reviewed);
CREATE INDEX IF NOT EXISTS idx_chat_messages_session ON chat_messages(session_id);
"""


def init_db():
    """Khởi tạo schema nếu chưa có (Phase 1 + Phase 2 + Phase 3 + Phase 4)."""
    conn = get_connection()
    try:
        conn.executescript(SCHEMA_SQL)
        conn.commit()  # executescript() tắt autocommit, cần commit thủ công

        # Seed document_types
        seed_doc_types(conn)

        # Cập nhật schema cho database cũ (nếu thiếu cột)
        try:
            conn.execute("ALTER TABLE documents ADD COLUMN relations_extracted INTEGER DEFAULT 0")
        except sqlite3.OperationalError: pass # Cột đã tồn tại

        try:
            conn.execute("ALTER TABLE documents ADD COLUMN embedding_indexed INTEGER DEFAULT 0")
        except sqlite3.OperationalError: pass # Cột đã tồn tại

        try:
            conn.execute("ALTER TABLE documents ADD COLUMN wiki_compiled INTEGER DEFAULT 0")
        except Exception: pass

        conn.commit()
        print("[DB] Schema ready (Phase 1 + Phase 2 + Phase 3 + Phase 4).")
    finally:
        conn.close()


def seed_doc_types(conn):
    """Nạp dữ liệu xếp hạng hiệu lực pháp lý mặc định."""
    default_types = [
        ("hien_phap", "Hiến pháp", 15),
        ("luat", "Luật", 14),
        ("bo_luat", "Bộ luật", 14),
        ("nghi_quyet_qh", "Nghị quyết của Quốc hội", 14),
        ("phap_lenh", "Pháp lệnh", 13),
        ("nghi_quyet_ubtvqh", "Nghị quyết của Ủy ban thường vụ Quốc hội", 13),
        ("lenh", "Lệnh của Chủ tịch nước", 12),
        ("quyet_dinh_ctn", "Quyết định của Chủ tịch nước", 12),
        ("nghi_dinh", "Nghị định của Chính phủ", 11),
        ("quyet_dinh_ttg", "Quyết định của Thủ tướng Chính phủ", 10),
        ("nghi_quyet_hdtp", "Nghị quyết của Hội đồng Thẩm phán Tòa án nhân dân tối cao", 9),
        ("thong_tu", "Thông tư", 8),
        ("nghi_quyet_hdnd_tinh", "Nghị quyết của Hội đồng nhân dân cấp tỉnh", 7),
        ("quyet_dinh_ubnd_tinh", "Quyết định của Ủy ban nhân dân cấp tỉnh", 6),
        ("vban_qppl_dac_biet", "Văn bản quy phạm pháp luật của chính quyền địa phương đặc biệt", 5),
        ("nghi_quyet_hdnd_huyen", "Nghị quyết của Hội đồng nhân dân cấp huyện", 4),
        ("quyet_dinh_ubnd_huyen", "Quyết định của Ủy ban nhân dân cấp huyện", 3),
        ("nghi_quyet_hdnd_xa", "Nghị quyết của Hội đồng nhân dân cấp xã", 2),
        ("quyet_dinh_ubnd_xa", "Quyết định của Ủy ban nhân dân cấp xã", 1),
        # Dự phòng
        ("quyet_dinh", "Quyết định", 6),
        ("nghi_quyet", "Nghị quyết", 7),
        ("cong_van", "Công văn", 3),
        ("chi_thi", "Chỉ thị", 6),
        ("an_le", "Án lệ", 9),
    ]
    for code, name, rank in default_types:
        conn.execute(
            "INSERT OR IGNORE INTO document_types (type_code, type_name, hierarchy_rank) VALUES (?, ?, ?)",
            (code, name, rank)
        )
    conn.commit()


def is_empty() -> bool:
    """Kiểm tra DB có dữ liệu chưa."""
    with get_db() as conn:
        row = conn.execute("SELECT COUNT(*) as cnt FROM documents").fetchone()
        return row["cnt"] == 0
