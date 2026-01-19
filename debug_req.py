
import requests
import io

url = "http://127.0.0.1:8000/api/projects/1/thumbnail/save"
files = {'file': ('test_thumb.png', b'test content', 'image/png')}

try:
    print(f"Sending POST to {url}...")
    resp = requests.post(url, files=files)
    print(f"Status: {resp.status_code}")
    print(f"Response: {resp.text}")
except Exception as e:
    print(f"Request failed: {e}")
