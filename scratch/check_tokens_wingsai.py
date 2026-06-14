import sqlite3
import os

db_path = r'data/wingsai.db'

print(f"--- Checking {db_path} ---")
try:
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
    tables = cursor.fetchall()
    for table in tables:
        print(f"  Table: {table[0]}")
        cursor.execute(f"PRAGMA table_info({table[0]})")
        columns = cursor.fetchall()
        col_names = [col[1] for col in columns]
        print(f"    Columns: {col_names}")
        
        if any(k in ' '.join(col_names).lower() for k in ['balance', 'token', 'credits']):
            print(f"    *** POTENTIAL TOKEN TABLE: {table[0]} ***")
            try:
                cursor.execute(f"SELECT * FROM {table[0]} ORDER BY rowid DESC LIMIT 10")
                rows = cursor.fetchall()
                for row in rows:
                    print(f"      Data: {row}")
            except:
                pass
    conn.close()
except Exception as e:
    print(f"  Error: {e}")
