
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

headers = {
    "apikey": key,
    "Authorization": f"Bearer {key}",
    "Content-Type": "application/json"
}

# In Supabase, we can check the table list via PostgREST metadata (or just try common names)
# But easier: try to fetch from pg_catalog if allowed, or just list common suspected tables.

tables = ["ai_logs", "ai_generation_logs", "token_transactions", "profiles"]

for table in tables:
    endpoint = f"{url}/rest/v1/{table}?limit=1"
    try:
        response = requests.get(endpoint, headers=headers)
        if response.status_code == 200:
            count = len(response.json())
            print(f"Table [{table}] exists, limit 1 count: {count}")
        elif response.status_code == 404:
            print(f"Table [{table}] does NOT exist")
        else:
            print(f"Table [{table}] status {response.status_code}: {response.text}")
    except Exception as e:
        print(f"Error checking {table}: {e}")
