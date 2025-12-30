import sqlite3
import os

def check_latest_project_video_path():
    db_path = os.path.join('data', 'wingsai.db')
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Get latest project
    cursor.execute("SELECT id, name, status FROM projects ORDER BY updated_at DESC LIMIT 1")
    project = cursor.fetchone()
    
    if not project:
        print("No projects found.")
        return

    pid, name, status = project
    print(f"Project ID: {pid}")
    print(f"Name: {name}")
    print(f"Status: {status}")
    p_video_path = None # Not in projects table
    
    # Check settings table
    cursor.execute("SELECT video_path FROM project_settings WHERE project_id = ?", (pid,))
    setting = cursor.fetchone()
    s_video_path = setting[0] if setting else None
    print(f"Settings Video Path: {s_video_path}")
    
    conn.close()
    
    # Check file existence
    target_path = s_video_path or p_video_path
    if target_path:
        print(f"Checking file: {target_path}")
        if os.path.exists(target_path):
            print(f"File exists. Size: {os.path.getsize(target_path)} bytes")
        else:
            print("File does NOT exist on disk.")
    else:
        print("No video path found.")

if __name__ == "__main__":
    check_latest_project_video_path()
