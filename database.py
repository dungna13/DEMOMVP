"""
database.py — SQLite + FTS5 setup cho Phase 1 MVP
Schema theo HLD: documents, doc_sections, chunks + FTS5 virtual table
"""

import sqlite3
import os
from contextlib import contextmanager

DB_PATH = os.path.join(os.path.dirname(__file__), "vanban.db")


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

-- ========== INDEXES ==========

CREATE INDEX IF NOT EXISTS idx_docs_number          ON documents(doc_number);
CREATE INDEX IF NOT EXISTS idx_docs_type            ON documents(doc_type);
CREATE INDEX IF NOT EXISTS idx_docs_effectiveness   ON documents(effectiveness_status);
CREATE INDEX IF NOT EXISTS idx_docs_effective_date  ON documents(issuing_date);
CREATE INDEX IF NOT EXISTS idx_sections_doc_type    ON doc_sections(document_id, section_type);
CREATE INDEX IF NOT EXISTS idx_chunks_doc           ON chunks(document_id);

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
"""


def init_db():
    """Khởi tạo schema nếu chưa có."""
    conn = get_connection()
    try:
        conn.executescript(SCHEMA_SQL)
        print("[DB] Schema ready.")
    finally:
        conn.close()


def is_empty() -> bool:
    """Kiểm tra DB có dữ liệu chưa."""
    with get_db() as conn:
        row = conn.execute("SELECT COUNT(*) as cnt FROM documents").fetchone()
        return row["cnt"] == 0

