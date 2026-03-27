import sqlite3
import json
import os
import sys

# Add path to finding database.py
sys.path.append(os.getcwd())
try:
    from database import get_db, get_image_prompts, get_project_full_data
except ImportError:
    print("Could not import database.py. Make sure you are in the right directory.")
    sys.exit(1)

def check_latest_project():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT id, name FROM projects ORDER BY id DESC LIMIT 1")
    row = cursor.fetchone()
    if not row:
        print("No projects found.")
        return
    
    project_id = row['id']
    project_name = row['name']
    print(f"Checking Project ID: {project_id} ({project_name})")
    
    # 1. Check raw table
    print("\n[Raw DB Check] 'image_prompts' table:")
    cursor.execute("SELECT count(*) as cnt FROM image_prompts WHERE project_id = ?", (project_id,))
    count = cursor.fetchone()['cnt']
    print(f"Count: {count}")
    
    cursor.execute("SELECT * FROM image_prompts WHERE project_id = ?", (project_id,))
    rows = cursor.fetchall()
    for r in rows:
        print(dict(r))

    # 2. Check get_image_prompts function
    print("\n[Function Check] get_image_prompts():")
    try:
        prompts = get_image_prompts(project_id)
        print(f"Result: {prompts}")
    except Exception as e:
        print(f"Error calling get_image_prompts: {e}")

    # 3. Check get_project_full_data function
    print("\n[Function Check] get_project_full_data():")
    try:
        full = get_project_full_data(project_id)
        if full:
            print(f"Keys: {full.keys()}")
            print(f"Image Prompts in Full: {full.get('image_prompts')}")
        else:
            print("Returned None")
    except Exception as e:
        print(f"Error calling get_project_full_data: {e}")

if __name__ == "__main__":
    check_latest_project()
