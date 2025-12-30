
import requests
import json

url = "http://127.0.0.1:8000/api/projects/5/render"
headers = {"Content-Type": "application/json"}
data = {
    "project_id": 5,
    "use_subtitles": True,
    "resolution": "720p"
}

try:
    response = requests.post(url, json=data, headers=headers)
    print(f"Status Code: {response.status_code}")
    print("Response Body:")
    print(response.text)
except Exception as e:
    print(e)
