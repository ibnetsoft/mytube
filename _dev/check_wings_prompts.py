import sqlite3
import os

def check_recent_prompts():
    db_path = r"c:\Users\kimse\Downloads\유튜브소재발굴기\롱폼생성기\data\wingsai.db"
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    cursor.execute("SELECT scene_number, prompt_en FROM image_prompts ORDER BY id DESC LIMIT 5")
    rows = cursor.fetchall()
    for row in rows:
        print(f"=== Scene {row['scene_number']} ===")
        print(row['prompt_en'])
        print("="*50)
    conn.close()

if __name__ == "__main__":
    check_recent_prompts()
