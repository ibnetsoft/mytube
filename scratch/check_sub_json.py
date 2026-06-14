import sqlite3
import json
import sys

sys.stdout.reconfigure(encoding='utf-8')

db_name = r'C:\Users\kimse\Downloads\YoutubeSourceFinder\LongformGenerator\data\wingsai.db'
conn = sqlite3.connect(db_name)
cursor = conn.cursor()
cursor.execute("SELECT subtitle_path FROM project_settings WHERE project_id = 190")
row = cursor.fetchone()
if row and row[0]:
    path = row[0]
    print(f"Subtitle path: {path}")
    with open(path, 'r', encoding='utf-8') as f:
        subs = json.load(f)
        if subs:
            print("First subtitle object:", json.dumps(subs[0], ensure_ascii=False, indent=2))
        else:
            print("Empty subtitles file")
else:
    print("Subtitle path not found for project 190")
conn.close()
