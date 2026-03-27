import sqlite3
import json
import os

PROJECT_ID = 67

def get_db_path():
    return os.path.join(os.path.dirname(__file__), "data", "wingsai.db")

conn = sqlite3.connect(get_db_path())
conn.row_factory = sqlite3.Row
cursor = conn.cursor()

cursor.execute("SELECT analysis_result FROM analysis WHERE project_id = ?", (PROJECT_ID,))
row = cursor.fetchone()
if row:
    res = row['analysis_result']
    if isinstance(res, str):
        try:
            res_json = json.loads(res)
            with open("debug_analysis_dump.json", "w", encoding="utf-8") as f:
                json.dump(res_json, f, indent=2, ensure_ascii=False)
            print("Dumped analysis result to debug_analysis_dump.json")
        except:
            print("Failed to parse analysis result JSON")
    else:
        print("Analysis result is not string")

conn.close()
