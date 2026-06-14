import sqlite3
import json

db_name = r'C:\Users\kimse\Downloads\YoutubeSourceFinder\LongformGenerator\data\wingsai.db'
conn = sqlite3.connect(db_name)
cursor = conn.cursor()
cursor.execute("SELECT name, script_vi, target_language, language FROM project_settings JOIN projects ON projects.id = project_settings.project_id WHERE projects.id = 190")
row = cursor.fetchone()
if row:
    print("Project 190 Info:")
    print(f"Name: {row[0]}")
    print(f"Script_vi Length: {len(row[1]) if row[1] else 'None'}")
    print(f"Target Language: {row[2]}")
    print(f"Language: {row[3]}")
    if row[1]:
        print("Script_vi Preview:", row[1][:300])
else:
    print("Project 190 not found")
conn.close()
