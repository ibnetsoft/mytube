import sqlite3
import os
from pathlib import Path

db_path = Path("data/wingsai.db")
if db_path.exists():
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()
    cursor.execute("UPDATE project_settings SET app_mode = 'shorts' WHERE app_mode = 'ko'")
    print(f"Updated {cursor.rowcount} projects to 'shorts'")
    conn.commit()
    conn.close()
else:
    print("DB not found")
