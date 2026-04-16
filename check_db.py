
import sqlite3
import json
from pathlib import Path
import sys

# Ensure UTF-8 output even on Windows
if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

def check_presets():
    try:
        # Correct path from database.py
        db_path = Path(__file__).parent / "data" / "wingsai.db"
        print(f"Checking DB at: {db_path}")
        
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        # 1. Check table existence
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='shorts_template_presets'")
        if not cursor.fetchone():
            print("TABLE NOT FOUND: shorts_template_presets")
            return
            
        # 2. Check counts
        cursor.execute("SELECT COUNT(*) as cnt FROM shorts_template_presets")
        count = cursor.fetchone()['cnt']
        print(f"Total Presets Found: {count}")
        
        # 3. List names
        cursor.execute("SELECT name, updated_at FROM shorts_template_presets")
        rows = cursor.fetchall()
        for row in rows:
            print(f" - [{row['name']}] Updated at: {row['updated_at']}")
            
        conn.close()
    except Exception as e:
        print(f"DB ERROR: {e}")

if __name__ == "__main__":
    check_presets()
