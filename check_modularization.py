
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
            # print(f"   Data type: {type(data)}")
            return True
        else:
            print(f"❌ Failed: {endpoint} returned {response.status_code}")
            try:
                print(f"   Response: {response.text[:200]}")
            except: pass
            return False
    except Exception as e:
        print(f"❌ Error connecting to {endpoint}: {e}")
        return False

if __name__ == "__main__":
    print("-" * 50)
    print("Testing Modularization State...")
    print("-" * 50)
    time.sleep(2) # Wait for server
    
    success = True
    
    # 1. Projects Router (/api/projects)
    print("\n[Testing Projects Router]")
    success &= check_endpoint("/api/projects")
    
    # 2. Settings Router (/api/settings)
    print("\n[Testing Settings Router]")
    success &= check_endpoint("/api/settings/style-presets")
    success &= check_endpoint("/api/settings/script-style-presets")
    
    # 3. Main Route (/api/health)
    print("\n[Testing Main Router]")
    success &= check_endpoint("/api/health") # Assuming this exists
    
    print("-" * 50)
    if success:
        print("🎉 All Critical Endpoints Verified!")
    else:
        print("⚠️  Some Endpoints Failed. Check logs.")
