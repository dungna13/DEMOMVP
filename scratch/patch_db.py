"""Patch database.py to add wiki_pages table."""
PHASE3_SCHEMA = """
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

CREATE INDEX IF NOT EXISTS idx_wiki_slug     ON wiki_pages(slug);
CREATE INDEX IF NOT EXISTS idx_wiki_type     ON wiki_pages(page_type);
CREATE INDEX IF NOT EXISTS idx_wiki_doc_id   ON wiki_pages(document_id);
CREATE INDEX IF NOT EXISTS idx_wiki_reviewed ON wiki_pages(reviewed);
"""

with open("src/database/database.py", "r", encoding="utf-8") as f:
    content = f.read()

# Find marker (CRLF or LF compatible)
old_marker = 'END;\r\n"""\r\n'
new_marker = 'END;\r\n' + PHASE3_SCHEMA.replace('\n', '\r\n') + '"""\r\n'

if old_marker in content:
    content = content.replace(old_marker, new_marker, 1)
    print("Patched with CRLF")
elif 'END;\n"""\n' in content:
    content = content.replace('END;\n"""\n', 'END;\n' + PHASE3_SCHEMA + '"""\n', 1)
    print("Patched with LF")
else:
    print("ERROR: marker not found")
    import sys; sys.exit(1)

# Also update init_db to run ALTER TABLE for wiki_pages migration
alter_marker = '        print("[DB] Schema ready (Phase 1 + Phase 2).")'
alter_replacement = '''        try:
            conn.execute("ALTER TABLE documents ADD COLUMN wiki_compiled INTEGER DEFAULT 0")
        except Exception: pass
        print("[DB] Schema ready (Phase 1 + Phase 2 + Phase 3).")'''
content = content.replace(alter_marker, alter_replacement)

with open("src/database/database.py", "w", encoding="utf-8") as f:
    f.write(content)
print("Done.")
