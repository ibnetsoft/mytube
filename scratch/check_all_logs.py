
import os
import requests
from dotenv import load_dotenv

dotenv_path = os.path.join(os.getcwd(), 'auth-web', '.env.local')
load_dotenv(dotenv_path=dotenv_path)

url = os.getenv("NEXT_PUBLIC_SUPABASE_URL")
key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")

if not url or not key:
    print(f"Error: Missing credentials")
    exit(1)

print("Fetching latest 5 logs from ai_logs to see the data structure...")

headers = {
    "apikey": key,
    "Authorization": f"Bearer {key}",
    "Content-Type": "application/json"
}

endpoint = f"{url}/rest/v1/ai_logs?select=user_id,created_at,task_type&order=created_at.desc&limit=10"

try:
    response = requests.get(endpoint, headers=headers)
    if response.status_code == 200:
        logs = response.json()
        print(f"Total across all users: {len(logs)}")
        for log in logs:
            uid = log.get('user_id')
            print(f"- {log.get('created_at')} | UserID: {uid} | Task: {log.get('task_type')}")
            
    else:
        print(f"Error: {response.status_code} - {response.text}")
except Exception as e:
    print(f"Request Error: {e}")
