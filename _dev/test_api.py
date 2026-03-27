import requests
import json

# Test API endpoint
url = "http://localhost:8000/api/settings/style-presets"

try:
    response = requests.get(url)
    print(f"Status Code: {response.status_code}")
    print(f"\nResponse:")
    data = response.json()
    print(json.dumps(data, indent=2, ensure_ascii=False))
    print(f"\nTotal presets: {len(data)}")
except Exception as e:
    print(f"Error: {e}")
