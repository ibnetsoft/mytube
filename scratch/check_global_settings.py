import os
import requests
from dotenv import load_dotenv

load_dotenv()

supabase_url = os.getenv("NEXT_PUBLIC_SUPABASE_URL")
supabase_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")

headers = {
    "apikey": supabase_key,
    "Authorization": f"Bearer {supabase_key}"
}
url = f"{supabase_url.rstrip('/')}/rest/v1/global_settings"

try:
    r = requests.get(url, headers=headers, timeout=5, verify=False, proxies={"http": None, "https": None})
    print("Status:", r.status_code)
    print("Data:", r.json())
except Exception as e:
    print("Error:", e)
