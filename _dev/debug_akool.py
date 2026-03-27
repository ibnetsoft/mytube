import asyncio
import os
import sys
import httpx
from dotenv import load_dotenv

# Add current dir to sys.path
sys.path.append(os.getcwd())

from services.akool_service import akool_service

load_dotenv()

async def debug_akool():
    print("--- Debugging AKOOL ---")
    print(f"Client ID: {akool_service.client_id}")
    # mask secret
    secret = akool_service.client_secret
    masked_secret = secret[:4] + "*" * (len(secret)-8) + secret[-4:] if len(secret) > 8 else "****"
    print(f"Client Secret (masked): {masked_secret}")
    
    url = "https://openapi.akool.com/api/open/v3/content/image/createbyprompt"
    headers = {
        "x-api-key": akool_service.api_key,
        "Content-Type": "application/json"
    }
    
    payload = {
        "prompt": "a cute cat",
        "size": "1:1",
        "model": "stable-diffusion-xl"
    }
    
    print(f"Using x-api-key: {headers['x-api-key'][:4]}...")
    
    async with httpx.AsyncClient(timeout=60.0) as client:
        resp = await client.post(url, json=payload, headers=headers)
        print(f"Status: {resp.status_code}")
        print(f"Body: {resp.text}")

if __name__ == "__main__":
    asyncio.run(debug_akool())
