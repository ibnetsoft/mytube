import sqlite3
import os

DB_PATH = "data/wingsai.db"
if os.path.exists(DB_PATH):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    print("--- Triggers ---")
    cursor.execute("SELECT name, sql FROM sqlite_master WHERE type='trigger'")
    for row in cursor.fetchall():
        print(f"Name: {row[0]}\nSQL: {row[1]}")
    
    print("\n--- Views ---")
    cursor.execute("SELECT name, sql FROM sqlite_master WHERE type='view'")
    for row in cursor.fetchall():
        print(f"Name: {row[0]}\nSQL: {row[1]}")
        
    conn.close()
else:
    print("DB not found")
