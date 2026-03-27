import sqlite3
from pathlib import Path

DB_PATH = Path("data/wingsai.db")
conn = sqlite3.connect(str(DB_PATH))
cur = conn.cursor()
cur.execute("PRAGMA table_info(project_settings)")
cols = cur.fetchall()
for col in cols:
    print(col[1])
conn.close()
