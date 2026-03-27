
import sqlite3
import os

DB_PATH = "data/wingsai.db"

def check_latest_project_script():
    if not os.path.exists(DB_PATH):
        print("DB not found")
        return

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    # Get latest project
    cursor.execute("SELECT id, name, created_at FROM projects ORDER BY id DESC LIMIT 1")
    project = cursor.fetchone()
    
    if not project:
        print("No projects found")
        return

    pid = project['id']
    print(f"Latest Project: ID={pid}, Title={project['name']}")
    
    # Get script
    cursor.execute("SELECT full_script FROM scripts WHERE project_id = ?", (pid,))
    script = cursor.fetchone()
    
    if script:
        text = script['full_script']
        print(f"Script Length: {len(text) if text else 0}")
        print("-" * 20)
        print(text[:500] if text else "Is NULL")
        print("-" * 20)
        
        if "신맞고" in text:
            print("[CONFIRMED] '신맞고' exists in script.")
        else:
            print("[WARNING] '신맞고' NOT found in script.")
            
    else:
        print("No script found for this project")

if __name__ == "__main__":
    check_latest_project_script()
