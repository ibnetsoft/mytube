import sqlite3
import os

db_path = "data/wingsai.db"
if os.path.exists(db_path):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = [r[0] for r in cursor.fetchall()]
    for t in tables:
        print(f"Table: {t}")
        cursor.execute(f"PRAGMA table_info({t})")
        cols = cursor.fetchall()
        for c in cols:
            print(f"  Column: {c[1]}")
    conn.close()
else:
    print("DB not found")
