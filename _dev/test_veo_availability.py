
import asyncio
import os
import httpx
from dotenv import load_dotenv

load_dotenv()
API_KEY = os.getenv("GEMINI_API_KEY")

async def test_veo():
    url = f"https://generativelanguage.googleapis.com/v1beta/models/veo-2.0-generate-001:predict?key={API_KEY}" 
    # Note: Endpoint guess based on naming convention (imagen-3.0, gemini-1.5). Actually Veo might be different.
    # Official docs say: https://generativelanguage.googleapis.com/v1beta/models/...
    # Let's try listing models first.
    
    list_url = f"https://generativelanguage.googleapis.com/v1beta/models?key={API_KEY}"
    async with httpx.AsyncClient() as client:
        resp = await client.get(list_url)
        data = resp.json()
        print("Available Models:")
        for m in data.get('models', []):
            if 'video' in m['name'] or 'veo' in m['name']:
                print(m['name'])

if __name__ == "__main__":
    asyncio.run(test_veo())
