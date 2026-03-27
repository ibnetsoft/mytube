
import httpx
import asyncio

async def test_endpoint():
    url = "http://127.0.0.1:8000/api/image/generate"
    payload = {
        "prompt": "A test image request",
        "project_id": 1,
        "scene_number": 1,
        "style": "realistic"
    }
    
    print(f"Calling endpoint: {url}")
    async with httpx.AsyncClient(timeout=60.0) as client:
        try:
            response = await client.post(url, json=payload)
            print(f"Status: {response.status_code}")
            # print(response.json()) 
            # We mostly care about the server logs print, but let's see response too.
            if response.status_code == 200:
                print("Success")
            else:
                print(f"Failed: {response.text}")
        except Exception as e:
            print(f"Connection error: {e}")

if __name__ == "__main__":
    asyncio.run(test_endpoint())
