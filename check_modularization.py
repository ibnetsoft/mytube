
import requests
import time
from config import config

BASE_URL = f"http://{config.HOST}:{config.PORT}"

def check_endpoint(endpoint):
    url = f"{BASE_URL}{endpoint}"
    print(f"Checking {url}...")
    try:
        response = requests.get(url, timeout=5)
        if response.status_code == 200:
            print(f"✅ Success: {endpoint} returned 200")
            data = response.json()
            # print(f"   Data keys: {list(data.keys()) if isinstance(data, dict) else len(data)}")
            return True
        else:
            print(f"❌ Failed: {endpoint} returned {response.status_code}")
            return False
    except Exception as e:
        print(f"❌ Error connecting to {endpoint}: {e}")
        return False

if __name__ == "__main__":
    print(f"Waiting for server {BASE_URL}...")
    time.sleep(2) # Wait a bit for server reload if needed
    
    # Check Style Presets (Moved to app/routers/settings.py)
    success = True
    success &= check_endpoint("/api/settings/style-presets")
    success &= check_endpoint("/api/settings/script-style-presets")
    
    # Check if main server is still alive (Health check)
    success &= check_endpoint("/api/health") # Assuming this exists or base path
    
    if success:
        print("\n🎉 Modularization Verification Passed!")
    else:
        print("\n⚠️  Modularization Verification Failed.")
