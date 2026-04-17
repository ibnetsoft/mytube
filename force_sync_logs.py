import sqlite3
import requests
import os
from pathlib import Path

# Config
DB_PATH = Path("data/wingsai.db")
LICENSE_PATH = Path("license.key")
DASHBOARD_URL = "http://localhost:3000" # Local test first, then can use production

def sync_logs():
    if not DB_PATH.exists():
        print("DB not found")
        return
    if not LICENSE_PATH.exists():
        print("License not found")
        return
        
    with open(LICENSE_PATH) as f:
        user_id = f.read().strip()
    
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    cursor.execute("SELECT * FROM ai_generation_logs")
    logs = cursor.fetchall()
    conn.close()
    
    print(f"Syncing {len(logs)} logs to Supabase for user {user_id}...")
    
    success_count = 0
    fail_count = 0
    
    for l in logs:
        payload = {
            "userId": user_id,
            "task_type": l['task_type'],
            "model_id": l['model_id'],
            "provider": l['provider'],
            "status": l['status'],
            "prompt_summary": l['prompt_summary'],
            "error_msg": l['error_msg'],
            "elapsed_time": l['elapsed_time'],
            "input_tokens": l['input_tokens'],
            "output_tokens": l['output_tokens']
        }
        
        try:
            # Sync to local first to verify, then can try production if needed
            resp = requests.post(f"{DASHBOARD_URL}/api/logs", json=payload, timeout=5)
            if resp.status_code == 200:
                success_count += 1
            else:
                print(f"Failed to sync {l['task_type']}: {resp.text}")
                fail_count += 1
        except Exception as e:
            print(f"Error syncing {l['task_type']}: {e}")
            fail_count += 1
            
    print(f"Sync Complete: {success_count} succeeded, {fail_count} failed.")

if __name__ == "__main__":
    sync_logs()
