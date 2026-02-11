import sqlite3
import os

try:
    db_path = os.path.join(os.path.dirname(__file__), "data", "wingsai.db")
    print(f"Connecting to database at: {db_path}")
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT id, name, topic, created_at FROM projects WHERE name LIKE '%비트코인%' OR topic LIKE '%비트코인%' ORDER BY created_at DESC LIMIT 5")
    rows = cursor.fetchall()
    print("Found projects:")
    for row in rows:
        print(row)
    conn.close()
except Exception as e:
    print(f"Error: {e}")
