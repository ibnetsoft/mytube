
import requests
import json
import sys

# API Endpoint URL
url = "http://127.0.0.1:8000/api/image/generate-prompts"

# Mock Payload
payload = {
    "script": "옛날 옛적에 호랑이가 살았습니다. 떡 하나 주면 안 잡아먹지.",
    "style": "wimpy",
    "count": 5,
    "project_id": 1
}

try:
    print(f"Testing POST {url}")
    response = requests.post(url, json=payload, timeout=120)
    
    print(f"Status Code: {response.status_code}")
    print("Response Headers:", response.headers)
    
    try:
        print("Response JSON:", json.dumps(response.json(), indent=2, ensure_ascii=False))
    except:
        print("Response Text:", response.text)

except Exception as e:
    print(f"Request Error: {e}")
