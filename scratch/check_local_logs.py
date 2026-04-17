
import sqlite3
import os

db_path = os.path.join(os.getcwd(), "data", "wingsai.db")
if not os.path.exists(db_path):
    # Try alternate path
    db_path = os.path.join(os.path.dirname(os.getcwd()), "data", "wingsai.db")

if not os.path.exists(db_path):
    print(f"Error: DB not found at {db_path}")
    exit(1)

print(f"Checking local DB: {db_path}")

conn = sqlite3.connect(db_path)
conn.row_factory = sqlite3.Row
cursor = conn.cursor()

try:
    cursor.execute("SELECT count(*) FROM ai_generation_logs")
    count = cursor.fetchone()[0]
    print(f"Total local logs: {count}")
    
    cursor.execute("SELECT * FROM ai_generation_logs ORDER BY created_at DESC LIMIT 5")
    rows = cursor.fetchall()
    for row in rows:
        print(f"- {row['created_at']} | {row['task_type']} | {row['status']} | {row['model_id']}")
except Exception as e:
    print(f"Error: {e}")
finally:
    conn.close()
