import sqlite3
from pathlib import Path

DB_PATH = Path("data/wingsai.db")
conn = sqlite3.connect(str(DB_PATH))
cur = conn.cursor()
cur.execute("SELECT app_mode, creation_mode FROM project_settings LIMIT 10")
rows = cur.fetchall()
for row in rows:
    print(f"app_mode: {row[0]}, creation_mode: {row[1]}")
conn.close()
