import sqlite3
import os

def check_scene_25():
    db_path = r"c:\Users\kimse\Downloads\유튜브소재발굴기\롱폼생성기\data\wingsai.db"
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    cursor.execute("SELECT prompt_en FROM image_prompts WHERE scene_number = 25 ORDER BY id DESC LIMIT 1")
    row = cursor.fetchone()
    if row:
        print("PROMPT_EN_START")
        print(row['prompt_en'])
        print("PROMPT_EN_END")
    else:
        print("Scene 25 not found")
    conn.close()

if __name__ == "__main__":
    check_scene_25()
