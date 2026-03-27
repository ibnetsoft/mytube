import asyncio
import os
from services.gemini_service import gemini_service

async def test_models():
    models = ["imagen-3", "imagen-3.0-generate-001", "imagen-4.0-generate-001"]
    for m in models:
        print(f"Testing {m}...")
        try:
            # Mocking generate_image logic for a specific model
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{m}:predict?key={gemini_service.api_key}"
            import httpx
            async with httpx.AsyncClient(timeout=10) as client:
                res = await client.post(url, json={"instances": [{"prompt": "test"}], "parameters": {"sampleCount": 1}})
                print(f"  Result: {res.status_code}")
                if res.status_code == 200:
                    print(f"  ✅ {m} IS WORKING")
                else:
                    print(f"  ❌ {m} failed: {res.text[:100]}")
        except Exception as e:
            print(f"  ❌ {m} error: {e}")

if __name__ == "__main__":
    asyncio.run(test_models())
