import sqlite3
import os

DB_PATH = "data/wingsai.db"
if os.path.exists(DB_PATH):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    try:
        print("Testing SELECT * FROM project_settings...")
        cursor.execute("SELECT * FROM project_settings LIMIT 1")
        row = cursor.fetchone()
        if row:
            print("Successfully fetched a row.")
            # Print column names
            cursor.execute("PRAGMA table_info(project_settings)")
            cols = [c[1] for c in cursor.fetchall()]
            print(f"Columns: {cols}")
        else:
            print("No rows found, but query succeeded.")
    except Exception as e:
        print(f"FAILED: {e}")
    conn.close()
else:
    print("DB not found")
