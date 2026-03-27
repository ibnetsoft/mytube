import sqlite3
import os

DB_PATH = "data/wingsai.db"
if os.path.exists(DB_PATH):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    for table in ["script_style_presets", "thumbnail_style_presets", "style_presets"]:
        print(f"--- {table} ---")
        try:
            cursor.execute(f"PRAGMA table_info({table})")
            [print(c) for c in cursor.fetchall()]
        except Exception as e:
            print(f"Error: {e}")
            
    conn.close()
else:
    print("DB not found")
