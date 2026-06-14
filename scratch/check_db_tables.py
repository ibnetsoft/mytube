import sqlite3
import os

db_name = r'C:\Users\kimse\Downloads\YoutubeSourceFinder\LongformGenerator\data\wingsai.db'
if not os.path.exists(db_name):
    print(f"{db_name} does not exist")
else:
    try:
        conn = sqlite3.connect(db_name)
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = [r[0] for r in cursor.fetchall()]
        print(f'{db_name} tables: {tables}')
        for table in tables:
            cursor.execute(f"PRAGMA table_info({table})")
            cols = [c[1] for c in cursor.fetchall()]
            print(f'  Table {table} columns: {cols}')
        conn.close()
    except Exception as e:
        print(f'{db_name} failed: {e}')
