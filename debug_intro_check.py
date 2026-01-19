import sqlite3
import json
import os
from pathlib import Path

DB_PATH = Path("data") / "wingsai.db"

def check_intro_path():
    if not DB_PATH.exists():
        print(f"DB not found at {DB_PATH}")
        return

    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # Get latest project
    cursor.execute("SELECT id, name, created_at FROM projects ORDER BY created_at DESC LIMIT 1")
    project = cursor.fetchone()
    
    if not project:
        print("No projects found")
        conn.close()
        return

    print(f"Project Code: {project['id']} ({project['name']})")

    # Get settings
    cursor.execute("SELECT intro_video_path, background_video_url FROM project_settings WHERE project_id = ?", (project['id'],))
    settings = cursor.fetchone()
    
    if settings:
        print(f"intro_video_path: {settings['intro_video_path']}")
        print(f"background_video_url: {settings['background_video_url']}")
    else:
        print("No settings found")

    conn.close()

if __name__ == "__main__":
    check_intro_path()
