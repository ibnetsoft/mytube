import sqlite3
import os

DB_PATH = "data/wingsai.db"
if os.path.exists(DB_PATH):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    print("--- global_settings ---")
    cursor.execute("PRAGMA table_info(global_settings)")
    [print(c) for c in cursor.fetchall()]
    
    print("--- project_settings ---")
    cursor.execute("PRAGMA table_info(project_settings)")
    [print(c) for c in cursor.fetchall()]
    
    print("--- commerce_videos ---")
    try:
        cursor.execute("PRAGMA table_info(commerce_videos)")
        [print(c) for c in cursor.fetchall()]
    except:
        print("commerce_videos not found")
        
    conn.close()
else:
    print("DB not found")
