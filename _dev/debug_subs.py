
import json
import os
import database as db

PID = 15

print("--- Simulating get_subtitles logic ---")
try:
    s = db.get_project_settings(PID)
    path = s.get('subtitle_path')
    print(f"Path: {path}")

    if path and os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
            print(f"Data Type: {type(data)}")
            print(f"Data Length: {len(data) if isinstance(data, list) else 'Not List'}")
            if isinstance(data, list) and len(data) > 0:
                print(f"First Item: {data[0]}")
    else:
        print("Path does not exist")
except Exception as e:
    print(f"Error: {e}")
