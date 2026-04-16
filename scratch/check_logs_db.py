import sqlite3
import os

db_path = "data/wingsai.db"
if not os.path.exists(db_path):
    print(f"DB not found at {db_path}")
    exit(1)

conn = sqlite3.connect(db_path)
conn.row_factory = sqlite3.Row
cursor = conn.cursor()

print("--- AI Generation Logs (Last 10) ---")
cursor.execute("SELECT * FROM ai_generation_logs ORDER BY created_at DESC LIMIT 10")
rows = cursor.fetchall()
for row in rows:
    print(dict(row))

cursor.execute("SELECT COUNT(*) as cnt FROM ai_generation_logs")
count = cursor.fetchone()['cnt']
print(f"\nTotal Logs: {count}")

conn.close()
