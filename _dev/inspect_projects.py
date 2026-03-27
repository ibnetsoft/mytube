import sqlite3
import os

DB_PATH = "data/wingsai.db"
if os.path.exists(DB_PATH):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    print("--- projects ---")
    cursor.execute("PRAGMA table_info(projects)")
    [print(c) for c in cursor.fetchall()]
    conn.close()
else:
    print("DB not found")
