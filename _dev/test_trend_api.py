import requests
import json

try:
    response = requests.get("http://localhost:8000/api/trends/keywords?language=ko&period=now&age=all")
    print(f"Status: {response.status_code}")
    print(f"Response: {response.text[:500]}")
    
    if response.status_code == 200:
        data = response.json()
        print(f"\nKeywords count: {len(data.get('keywords', []))}")
        if data.get('keywords'):
            print(f"First 3 keywords: {data['keywords'][:3]}")
    else:
        print(f"Error: {response.text}")
except Exception as e:
    print(f"Exception: {e}")
