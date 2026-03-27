
import httpx

try:
    res = httpx.get("http://localhost:8000/api/health")
    print(f"Health check: {res.status_code}")
    print(res.json())
except Exception as e:
    print(f"Health check failed: {e}")
