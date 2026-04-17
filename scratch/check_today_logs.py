
import sqlite3
import os
from datetime import datetime

db_path = os.path.join(os.getcwd(), "data", "wingsai.db")
conn = sqlite3.connect(db_path)
conn.row_factory = sqlite3.Row
cursor = conn.cursor()

print(f"Checking local logs for today (2026-04-16)...")

try:
    cursor.execute("SELECT * FROM ai_generation_logs WHERE created_at LIKE '2026-04-16%' ORDER BY created_at DESC")
    rows = cursor.fetchall()
    print(f"Found {len(rows)} logs for today.")
    for row in rows:
        print(f"- {row['created_at']} | {row['task_type']} | {row['status']} | {row['error_msg']}")
except Exception as e:
    print(f"Error: {e}")
finally:
    conn.close()
