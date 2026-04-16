import sqlite3
import os

db_path = "data/wingsai.db"
if os.path.exists(db_path):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM ai_generation_logs ORDER BY created_at DESC LIMIT 10")
    rows = cursor.fetchall()
    for row in rows:
        print(dict(row))
    conn.close()
else:
    print(f"File not found: {db_path}")
