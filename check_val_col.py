import sqlite3

def check_schema():
    for db_name in ['database.db', 'db.sqlite3']:
        try:
            conn = sqlite3.connect(db_name)
            cursor = conn.cursor()
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
            tables = cursor.fetchall()
            print(f"\n--- {db_name} ---")
            for table in tables:
                table_name = table[0]
                cursor.execute(f"PRAGMA table_info({table_name});")
                cols = cursor.fetchall()
                for col in cols:
                    if col[1] == 'val':
                        print(f"FOUND 'val' column in table: {table_name}")
            conn.close()
        except Exception as e:
            print(f"Error checking {db_name}: {e}")

if __name__ == "__main__":
    check_schema()
