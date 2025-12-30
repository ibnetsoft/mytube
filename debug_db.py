import sqlite3
import json

def check_db():
    import os
    db_path = os.path.join(os.path.dirname(__file__), "data", "wingsai.db")
    print(f"Connecting to: {db_path}")
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    print("=== Projects ===")
    cursor.execute("SELECT id, name, topic FROM projects")
    for row in cursor.fetchall():
        print(row)
        
    print("\n=== Script Structure ===")
    try:
        cursor.execute("SELECT project_id, hook, style FROM script_structure")
        for row in cursor.fetchall():
            print(row)
    except Exception as e:
        print(f"Error reading structure: {e}")
        
    print("\n=== Script Structure (Sections Length) ===")
    try:
        cursor.execute("SELECT project_id, sections FROM script_structure")
        for row in cursor.fetchall():
            pid, sections = row
            try:
                sec_len = len(json.loads(sections)) if sections else 0
                print(f"Project {pid}: {sec_len} sections")
                # print(f"Preview: {sections[:100]}...")
            except:
                print(f"Project {pid}: Parse Error")
    except Exception as e:
         print(f"Error reading sections: {e}")

    conn.close()

if __name__ == "__main__":
    check_db()
