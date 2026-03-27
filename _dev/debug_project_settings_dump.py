import sqlite3
import json
import os

PROJECT_ID = 67

def get_db_path():
    return os.path.join(os.path.dirname(__file__), "data", "wingsai.db")

conn = sqlite3.connect(get_db_path())
conn.row_factory = sqlite3.Row
cursor = conn.cursor()

cursor.execute("SELECT * FROM project_settings WHERE project_id = ?", (PROJECT_ID,))
row = cursor.fetchone()
if row:
    print(f"\n[Project Settings for {PROJECT_ID}]")
    row_dict = dict(row)
    with open("debug_settings_dump.json", "w", encoding="utf-8") as f:
        json.dump(row_dict, f, indent=2, ensure_ascii=False)
    print("Dumped settings to debug_settings_dump.json")
else:
    print("No project settings found")

conn.close()
