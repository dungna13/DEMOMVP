import sqlite3
import sys

# Set output to utf-8
sys.stdout.reconfigure(encoding='utf-8')

db_path = "vanban.db"
conn = sqlite3.connect(db_path)
conn.row_factory = sqlite3.Row
rows = conn.execute("SELECT id, doc_number, title FROM documents LIMIT 50").fetchall()
for row in rows:
    print(f"{row['id']}: {row['doc_number']} - {row['title']}")
conn.close()
