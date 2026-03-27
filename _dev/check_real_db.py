import sqlite3
import os

def check_db():
    db_path = r"c:\Users\kimse\Downloads\유튜브소재발굴기\롱폼생성기\data\wingsai.db"
    if not os.path.exists(db_path):
        print(f"Error: {db_path} not found")
        return
        
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    
    c.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = c.fetchall()
    print(f"Tables: {tables}")
    
    if ('global_settings',) in tables:
        c.execute("SELECT key, value FROM global_settings")
        rows = c.fetchall()
        for key, val in rows:
            if any(s in key.lower() for s in ["token", "secret", "pass", "key"]):
                print(f"{key}: [HIDDEN, len={len(str(val)) if val else 0}]")
            else:
                print(f"{key}: {val}")
    else:
        print("global_settings table not found")
        
    conn.close()

if __name__ == "__main__":
    check_db()
