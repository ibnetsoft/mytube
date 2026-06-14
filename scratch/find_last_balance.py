import sqlite3
import os

db_path = r'data/wingsai.db'

try:
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM ai_generation_logs WHERE balance_after > 0 ORDER BY id DESC LIMIT 5")
    rows = cursor.fetchall()
    print("Recent non-zero balances:")
    for row in rows:
        print(row)
    conn.close()
except Exception as e:
    print(f"Error: {e}")
