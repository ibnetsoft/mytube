import requests
import json

try:
    print("Fetching FULL data for Project ID 11...")
    response = requests.get('http://127.0.0.1:8000/api/projects/11/full')
    if response.status_code == 200:
        data = response.json()
        settings = data.get('settings', {})
        bg_url = settings.get('background_video_url')
        print(f"\n[Settings Check]")
        print(f"background_video_url: {repr(bg_url)}")
        
        if bg_url:
            print("✅ FULL API returns background_video_url")
        else:
            print("❌ FULL API MISSING background_video_url")
    else:
        print(f"Error: {response.status_code} {response.text}")
except Exception as e:
    print(f"Exception: {e}")
