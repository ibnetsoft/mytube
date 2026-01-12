import requests
import urllib.parse

try:
    project_id = 11
    key = "background_video_url"
    value = "https://images.pexels.com/videos/TEST_PATCH/video.mp4"
    
    # Simulate API.js behavior
    encoded_value = urllib.parse.quote(value)
    url = f"http://127.0.0.1:8000/api/projects/{project_id}/settings/{key}?value={encoded_value}"
    
    print(f"PATCH URL: {url}")
    
    response = requests.patch(url)
    
    if response.status_code == 200:
        print("✅ PATCH Success")
        print(response.json())
        
        # Verify it actually stuck
        check = requests.get(f"http://127.0.0.1:8000/api/projects/{project_id}/settings")
        saved = check.json().get('background_video_url')
        print(f"Saved Value: {saved}")
        
        if saved == value:
            print("✅ Value persisted correctly")
        else:
            print(f"❌ Value mismatch: {saved}")
            
    else:
        print(f"❌ PATCH Failed: {response.status_code} {response.text}")

except Exception as e:
    print(f"Exception: {e}")
