import requests
import json

# Force preview regeneration
url = "http://127.0.0.1:8000/api/preview/subtitle"
payload = {
    "text": "테스트 자막입니다 (Test)",
    "style_name": "Basic_White",
    "font_size": 60,
    "font_color": "white",
    "stroke_color": "black",
    "stroke_width": 5
}
try:
    print("Sending preview request...")
    res = requests.post(url, json=payload)
    print(f"Status: {res.status_code}")
    print(f"Response: {res.text}")
except Exception as e:
    print(f"Error: {e}")
