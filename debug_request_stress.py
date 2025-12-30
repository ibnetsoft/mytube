
import requests
import json

url = "http://127.0.0.1:8000/api/projects/5/render"
headers = {"Content-Type": "application/json"}

# Case 1: String ID
print("Case 1: String ID")
data = {
    "project_id": "5",
    "use_subtitles": True,
    "resolution": "720p"
}
try:
    response = requests.post(url, json=data, headers=headers)
    print(f"Status Code: {response.status_code}")
    if response.status_code != 200:
        print(response.text)
except Exception as e:
    print(e)

# Case 2: Missing Resolution (should default)
print("\nCase 2: Missing Resolution")
data = {
    "project_id": 5,
    "use_subtitles": True
}
try:
    response = requests.post(url, json=data, headers=headers)
    print(f"Status Code: {response.status_code}")
    if response.status_code != 200:
        print(response.text)
except Exception as e:
    print(e)
    
# Case 3: Extra Field (maybe forbid?)
print("\nCase 3: Extra Field")
data = {
    "project_id": 5,
    "use_subtitles": True,
    "resolution": "720p",
    "extra_field": "bad"
}
try:
    response = requests.post(url, json=data, headers=headers)
    print(f"Status Code: {response.status_code}")
    if response.status_code != 200:
        print(response.text)
except Exception as e:
    print(e)
