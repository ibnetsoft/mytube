import sqlite3
import os

def check_subtitle_path():
    db_path = os.path.join('data', 'wingsai.db')
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    cursor.execute("SELECT id, name FROM projects ORDER BY updated_at DESC LIMIT 1")
    project = cursor.fetchone()
    
    if project:
        pid = project['id']
        print(f"Project: {project['name']} (ID: {pid})")
        
        cursor.execute("SELECT subtitle_path, subtitle_style_enum FROM project_settings WHERE project_id = ?", (pid,))
        settings = cursor.fetchone()
        
        if settings:
            sub_path = settings['subtitle_path']
            print(f"Subtitle Path in DB: {sub_path}")
            if sub_path:
                print(f"Exists on disk: {os.path.exists(sub_path)}")
            else:
                print("Subtitle Path is NULL or Empty")
        else:
            print("No settings found")
            
    conn.close()

if __name__ == "__main__":
    check_subtitle_path()
