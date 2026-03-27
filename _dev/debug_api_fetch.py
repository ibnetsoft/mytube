import requests
import json

try:
    print("Fetching settings for Project ID 11...")
    response = requests.get('http://127.0.0.1:8000/api/projects/11/settings')
    if response.status_code == 200:
        print("\n[API Response]")
        print(json.dumps(response.json(), indent=2, ensure_ascii=False))
        
        data = response.json()
        if data.get('background_video_url'):
            print("\n✅ API returns background_video_url")
        else:
            print("\n❌ API MISSING background_video_url")
    else:
        print(f"Error: {response.status_code} {response.text}")
except Exception as e:
    print(f"Exception: {e}")
