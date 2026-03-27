
import requests

url = "http://127.0.0.1:8000/api/projects/1/full"
try:
    print(f"GET {url}")
    resp = requests.get(url)
    print(f"Status: {resp.status_code}")
    if resp.status_code == 200:
        print(resp.json())
    else:
        print(resp.text)
except Exception as e:
    print(e)
