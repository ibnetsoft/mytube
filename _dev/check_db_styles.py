import sqlite3
import json
from pathlib import Path

DB_PATH = Path(r"c:\Users\kimse\Downloads\유튜브소재발굴기\롱폼생성기\data\wingsai.db")

def check_styles():
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    print("--- script_style_presets ---")
    cursor.execute("SELECT * FROM script_style_presets")
    for row in cursor.fetchall():
        print(dict(row))
        
    print("\n--- style_presets (image) ---")
    cursor.execute("SELECT * FROM style_presets")
    for row in cursor.fetchall():
        print(dict(row))
        
    conn.close()

if __name__ == "__main__":
    check_styles()
