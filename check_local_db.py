import sqlite3
import os
from pathlib import Path

def check_local_logs():
    db_path = Path("data/wingsai.db")
    if not db_path.exists():
        print(f"DB File not found at {db_path}")
        return

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    try:
        cursor.execute("SELECT * FROM ai_generation_logs ORDER BY created_at DESC")
        rows = cursor.fetchall()
        print(f"Total Local Logs: {len(rows)}")
        for r in rows:
            print(f"[{r['created_at']}] {r['task_type']} | {r['status']} | {r['input_tokens'] + r['output_tokens']} TK")
    except Exception as e:
        print(f"Error: {e}")
    finally:
        conn.close()

check_local_logs()
