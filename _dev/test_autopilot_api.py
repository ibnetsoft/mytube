import httpx
import json

def test_autopilot_start():
    url = "http://localhost:8000/api/autopilot/start"
    payload = {
        "keyword": "테스트",
        "visual_style": "realistic",
        "thumbnail_style": "face",
        "video_scene_count": 1,
        "script_style": "story"
    }
    try:
        response = httpx.post(url, json=payload, timeout=30.0)
        print(f"Status: {response.status_code}")
        print(f"Response: {response.json()}")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    test_autopilot_start()
