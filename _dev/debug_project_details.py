import sqlite3
import json
import os

PROJECT_ID = 67

def get_db_path():
    return os.path.join(os.path.dirname(__file__), "data", "wingsai.db")

def fetch_data(table, project_id):
    try:
        conn = sqlite3.connect(get_db_path())
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute(f"SELECT * FROM {table} WHERE project_id = ?", (project_id,))
        row = cursor.fetchone()
        conn.close()
        if row:
            return dict(row)
        return None
    except Exception as e:
        print(f"Error fetching {table}: {e}")
        return None

print(f"--- Analyzing Project {PROJECT_ID} ---")

# 1. Check Analysis
analysis = fetch_data("analysis", PROJECT_ID)
if analysis:
    print("\n[Analysis Result]")
    res = analysis.get("analysis_result")
    try:
        if isinstance(res, str):
            res_json = json.loads(res)
            # Check for mention of '기안84' in comments or keywords
            print(json.dumps(res_json, indent=2, ensure_ascii=False))
        else:
            print(res)
    except:
        print("Raw analysis result:", res)
else:
    print("\n[Analysis] No data found.")

# 2. Check Structure
structure = fetch_data("script_structure", PROJECT_ID)
if structure:
    print("\n[Script Structure]")
    sections = structure.get("sections")
    print(sections) # Expecting JSON string or list
else:
    print("\n[Structure] No data found.")

# 3. Check Script
script = fetch_data("scripts", PROJECT_ID)
if script:
    print("\n[Script Content]")
    content = script.get("content")
    if content:
        # Find lines containing 기안84
        lines = content.split('\n')
        for i, line in enumerate(lines):
            if "기안84" in line:
                print(f"Line {i+1}: {line.strip()}")
    else:
        print("Script content empty.")
else:
    # Check project_settings as fallback
    settings = fetch_data("project_settings", PROJECT_ID)
    if settings and settings.get("script_content"):
         content = settings.get("script_content")
         if "기안84" in content:
             print(f"\n[Script from Settings] Found '기안84':")
             print(content)
    else:
        print("\n[Script] No data found.")
