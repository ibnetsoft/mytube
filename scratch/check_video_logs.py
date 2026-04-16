import sqlite3
import os

db_path = "data/wingsai.db"
if os.path.exists(db_path):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    # List distinct task_types to see what we have
    cursor.execute("SELECT DISTINCT task_type FROM ai_generation_logs")
    types = [row['task_type'] for row in cursor.fetchall()]
    print(f"Existing task_types: {types}")
    
    # Check specifically for video logs
    cursor.execute("SELECT * FROM ai_generation_logs WHERE task_type LIKE '%video%' OR task_type='veo' ORDER BY created_at DESC LIMIT 5")
    rows = cursor.fetchall()
    print("Recent video-related logs:")
    for row in rows:
        print(dict(row))
    conn.close()
else:
    print(f"File not found: {db_path}")
