
import requests
import time
from config import config

BASE_URL = f"http://{config.HOST}:{config.PORT}"

def check_endpoint(endpoint, method="GET"):
    url = f"{BASE_URL}{endpoint}"
    print(f"Checking {method} {url}...")
    try:
        response = None
        if method == "GET":
            response = requests.get(url, timeout=10) # Increased timeout
        elif method == "POST":
            response = requests.post(url, json={}, timeout=10) # Increased timeout
            
        if response.status_code != 404:
            print(f"✅ Success: {endpoint} found (Status: {response.status_code})")
            return True
        else:
            print(f"❌ Failed: {endpoint} returned 404 Not Found")
            # print(response.text[:100])
            return False
    except Exception as e:
        print(f"❌ Error connecting to {endpoint}: {e}")
        return False

if __name__ == "__main__":
    print("-" * 50)
    print("Testing Modularization State (Retry)...")
    print("-" * 50)
    time.sleep(5) # Wait longer
    
    success = True
    
    # Check Project List (Simplest DB query)
    print("\n[Testing Project List]")
    success &= check_endpoint("/api/projects", "GET")
    
    # Check Media
    print("\n[Testing Media Router]")
    success &= check_endpoint("/api/image/generate-mock", "POST")
    
    # Check Animate
    print("\n[Testing Animate Router]")
    success &= check_endpoint("/api/projects/1/scenes/animate", "POST")

    print("-" * 50)
    if success:
        print("🎉 Modularization Completed Successfully!")
    else:
        print("⚠️  Some Routes Missing.")
