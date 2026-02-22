import sqlite3
import os

DB_PATH = "data/wingsai.db"
if os.path.exists(DB_PATH):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("PRAGMA table_info(project_settings)")
    columns = cursor.fetchall()
    for col in columns:
        print(f"Col: {col[1]}, Type: {col[2]}")
    conn.close()
else:
    print("DB not found")
