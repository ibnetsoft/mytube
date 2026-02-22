import sqlite3
import os

for db_file in [f for f in os.listdir('.') if f.endswith('.db') or f.endswith('.sqlite3')]:
    print(f"Checking {db_file}...")
    try:
        conn = sqlite3.connect(db_file)
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = [r[0] for r in cursor.fetchall()]
        for t in tables:
            cursor.execute(f"PRAGMA table_info({t})")
            cols = cursor.fetchall()
            for c in cols:
                if c[1].lower() == 'val':
                    print(f"  FOUND 'val' in table '{t}'")
        conn.close()
    except Exception as e:
        print(f"  Error checking {db_file}: {e}")
