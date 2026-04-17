
import requests
import json

url = "http://localhost:3000/api/logs"
user_id = "ba2f2a43-c6ea-4fe2-a6a3-0f861d93afc6"

payload = {
    "userId": user_id,
    "task_type": "test_push",
    "model_id": "test_model",
    "provider": "test_provider",
    "status": "success",
    "prompt_summary": "Testing if push works from local to local auth-web",
    "elapsed_time": 1.5,
    "input_tokens": 100,
    "output_tokens": 200
}

print(f"Pushing test log to {url}...")
try:
    response = requests.post(url, json=payload, timeout=10)
    print(f"Status: {response.status_code}")
    print(f"Response: {response.text}")
except Exception as e:
    print(f"Error: {e}")
