import sqlite3
import os

db = 'data/wingsai.db'
if os.path.exists(db):
    try:
        conn = sqlite3.connect(db)
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM global_settings")
        print("Global Settings:", cursor.fetchall())
        conn.close()
    except Exception as e:
        print("Error:", e)
else:
    print("Database not found")
