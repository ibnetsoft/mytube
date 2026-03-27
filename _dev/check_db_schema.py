
import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(__file__), "data", "wingsai.db")

def check_db_schema():
    if not os.path.exists(DB_PATH):
        print(f"Database not found at {DB_PATH}")
        return

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    try:
        cursor.execute("PRAGMA table_info(image_prompts)")
        columns = cursor.fetchall()
        print("Columns in 'image_prompts':")
        for col in columns:
            print(f"- {col[1]}")
    except Exception as e:
        print(f"Error checking schema: {e}")
    finally:
        conn.close()

if __name__ == "__main__":
    check_db_schema()
