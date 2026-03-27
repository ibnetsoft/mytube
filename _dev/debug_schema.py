import sqlite3
import os

try:
    db_path = os.path.join(os.path.dirname(__file__), "data", "wingsai.db")
    print(f"Connecting to database at: {db_path}")
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("PRAGMA table_info(projects)")
    columns = cursor.fetchall()
    print("Columns in 'projects' table:")
    for col in columns:
        print(col)
    conn.close()
except Exception as e:
    print(f"Error: {e}")
