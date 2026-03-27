
import sys
import os
import json

# Add current dir to path
sys.path.append(os.getcwd())

from database import get_db

def check_images(project_id):
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT * FROM image_prompts WHERE project_id = ?", (project_id,))
        rows = cursor.fetchall()
        
        print(f"--- Project {project_id} Image Prompts (Count: {len(rows)}) ---")
        for row in rows:
            # Row is sqlite3.Row usually if set in get_db
            try:
                url = row['image_url']
            except:
                url = row[5] # Index 5 is image_url based on schema
            print(f"Scene {row['scene_number']}: {url}")
            
    except Exception as e:
        print(f"Error: {e}")
    finally:
        conn.close()

if __name__ == "__main__":
    check_images(1515)
