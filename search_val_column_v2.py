import sqlite3
import os

def check_db(db_path):
    print(f"Checking {db_path}...")
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = [r[0] for r in cursor.fetchall()]
        for t in tables:
            try:
                cursor.execute(f"PRAGMA table_info({t})")
                cols = cursor.fetchall()
                for c in cols:
                    if c[1].lower() == 'val':
                        print(f"  FOUND 'val' in table '{t}' of {db_path}")
            except Exception as te:
                print(f"    Error checking table {t}: {te}")
        conn.close()
    except Exception as e:
        print(f"  Error checking {db_path}: {e}")

# Search in current dir and data/ dir
dirs_to_check = ['.', 'data']
for d in dirs_to_check:
    if not os.path.exists(d): continue
    for f in os.listdir(d):
        if f.endswith('.db') or f.endswith('.sqlite3'):
            check_db(os.path.join(d, f))
