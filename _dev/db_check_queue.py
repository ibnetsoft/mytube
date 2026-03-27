import sqlite3
db_path = r'c:\Users\kimse\Downloads\유튜브소재발굴기\롱폼생성기\data\wingsai.db'
conn = sqlite3.connect(db_path)
conn.row_factory = sqlite3.Row
cursor = conn.cursor()
cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
tables = [r[0] for r in cursor.fetchall()]
print("Tables:", tables)

if "autopilot_queue" in tables:
    cursor.execute("SELECT * FROM autopilot_queue")
    rows = [dict(r) for r in cursor.fetchall()]
    print("Autopilot Queue Contents:", rows)
elif "queue" in tables:
    cursor.execute("SELECT * FROM queue")
    rows = [dict(r) for r in cursor.fetchall()]
    print("Queue Contents:", rows)
else:
    print("No obvious queue table found.")

conn.close()
