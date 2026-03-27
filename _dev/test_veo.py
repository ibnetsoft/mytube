import asyncio
import os
import base64
import httpx
from services.gemini_service import gemini_service

async def test_veo():
    print("--- TESTING VEO VIDEO GEN ---")
    url = f"{gemini_service.base_url}/models/veo-3.0-fast-generate-001:predict?key={gemini_service.api_key}"
    
    payload = {
        "instances": [{"prompt": "A cat running in a field"}],
        "parameters": {"sampleCount": 1}
    }
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            res = await client.post(url, json=payload)
            print(f"Status: {res.status_code}")
            if res.status_code == 200:
                print("✅ VEO IS WORKING")
            else:
                print(f"❌ VEO Failed: {res.text[:200]}")
        except Exception as e:
            print(f"❌ Error: {e}")

if __name__ == "__main__":
    asyncio.run(test_veo())
