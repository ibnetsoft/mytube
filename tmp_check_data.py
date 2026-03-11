
import sqlite3
import os

db_path = r"c:\Users\kimse\Downloads\유튜브소재발굴기\롱폼생성기\data\wingsai.db"

def check_db():
    if not os.path.exists(db_path):
        print(f"DB not found at {db_path}")
        return

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    try:
        print("--- Projects ---")
        cursor.execute("SELECT id, name, created_at FROM projects ORDER BY created_at DESC LIMIT 5")
        projects = cursor.fetchall()
        for p in projects:
            print(f"ID: {p['id']}, Name: {p['name']}, Created: {p['created_at']}")
            
            # Check image prompts for this project
            cursor.execute("SELECT count(*) as count FROM image_prompts WHERE project_id = ?", (p['id'],))
            count = cursor.fetchone()['count']
            print(f"  -> Image Prompts Count: {count}")
            
            if count > 0:
                cursor.execute("SELECT scene_number, scene_text, prompt_en FROM image_prompts WHERE project_id = ? LIMIT 2", (p['id'],))
                prompts = cursor.fetchall()
                for pr in prompts:
                    text_preview = pr['scene_text'][:50] if pr['scene_text'] else "N/A"
                    print(f"    Scene {pr['scene_number']}: {text_preview}")

    except Exception as e:
        print(f"Error: {e}")
    finally:
        conn.close()

if __name__ == "__main__":
    check_db()
