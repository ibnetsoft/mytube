import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent / "data" / "wingsai.db"
conn = sqlite3.connect(str(DB_PATH))
cursor = conn.cursor()

# Check style_presets table
cursor.execute('SELECT * FROM style_presets')
rows = cursor.fetchall()
print(f'style_presets - Total rows: {len(rows)}')
for row in rows:
    print(row)

print('\n--- Checking table schema ---')
cursor.execute("PRAGMA table_info(style_presets)")
schema = cursor.fetchall()
for col in schema:
    print(col)

conn.close()
