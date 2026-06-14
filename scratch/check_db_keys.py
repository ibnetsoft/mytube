import sqlite3
import os

db_path = r"c:\Users\kimse\Downloads\유튜브소재발굴기\롱폼생성기\data\wingsai.db"
if os.path.exists(db_path):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT * FROM global_settings")
        rows = cursor.fetchall()
        for row in rows:
            print(f"{row[0]}: {row[1]}")
    except Exception as e:
        print(f"Error: {e}")
    finally:
        conn.close()
else:
    print("DB not found")
