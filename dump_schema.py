import sqlite3
import os

DB_PATH = "data/wingsai.db"
if os.path.exists(DB_PATH):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = [row[0] for row in cursor.fetchall()]
    
    for table in tables:
        print(f"=== Table: {table} ===")
        cursor.execute(f"PRAGMA table_info({table})")
        cols = cursor.fetchall()
        for col in cols:
            print(f"  Col: {col[1]} ({col[2]})")
            if col[1].lower() == 'val':
                print(f"  !!! FOUND COLUMN 'val' in table {table} !!!")
    conn.close()
else:
    print("DB not found")
