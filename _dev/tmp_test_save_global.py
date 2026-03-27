
import httpx

data = {
    "app_mode": "longform",
    "wp_url": "https://pipmaker.co.kr",
    "wp_username": "피카디리",
    "wp_password": "dV5A CaNz 3MpT E0se mtMX xJAU"
}

try:
    res = httpx.post("http://localhost:8000/api/settings", json=data)
    print(f"Global Settings Save: {res.status_code}")
    print(res.json())
except Exception as e:
    print(f"Post failed: {e}")
