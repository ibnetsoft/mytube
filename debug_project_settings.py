import sqlite3
import json
import os

PROJECT_ID = 67

def get_db_path():
    return os.path.join(os.path.dirname(__file__), "data", "wingsai.db")

conn = sqlite3.connect(get_db_path())
conn.row_factory = sqlite3.Row
cursor = conn.cursor()

# Check project_settings
cursor.execute("SELECT * FROM project_settings WHERE project_id = ?", (PROJECT_ID,))
rows = cursor.fetchall()
if rows:
    print(f"\n[Project Settings] Found {len(rows)} entries")
    for row in rows:
        key = row['key']
        value = row['value']
        print(f"Key: {key}")
        if len(value) > 200:
            print(f"Value: {value[:200]}...")
        else:
            print(f"Value: {value}")
else:
    print("No project settings found")

conn.close()
