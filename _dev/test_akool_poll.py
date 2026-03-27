import asyncio
import os
import sys
import httpx
from dotenv import load_dotenv

# Add current dir to sys.path
sys.path.append(os.getcwd())

from services.akool_service import akool_service

load_dotenv()

async def test_akool_polling():
    print("--- Testing AKOOL Polling (v3) ---")
    url = "https://openapi.akool.com/api/open/v3/content/image/createbyprompt"
    headers = {
        "x-api-key": akool_service.api_key,
        "Content-Type": "application/json"
    }
    payload = {
        "prompt": "a landscape painting",
        "size": "1:1"
    }
    
    async with httpx.AsyncClient(timeout=60.0) as client:
        resp = await client.post(url, json=payload, headers=headers)
        res = resp.json()
        if res.get("code") != 1000:
            print(f"FAILED: {res}")
            return
        
        job_id = res["data"]["_id"]
        print(f"JOB ID: {job_id}")
        
        # Poll
        poll_url = "https://openapi.akool.com/api/open/v3/content/image/resultsByIds"
        for _ in range(10):
            await asyncio.sleep(3)
            poll_resp = await client.post(poll_url, json={"_ids": job_id}, headers=headers)
            poll_res = poll_resp.json()
            print(f"Status: {poll_resp.status_code}, Body: {poll_resp.text}")
            
            results = poll_res.get("data", {}).get("result", [])
            if results:
                item = results[0]
                # status 3=done, 4=fail
                if item.get("status") == 3:
                     print(f"SUCCESS: {item.get('url') or item.get('images', [None])[0]}")
                     return
                elif item.get("status") == 4:
                     print(f"FAILED JOB: {item}")
                     return

if __name__ == "__main__":
    asyncio.run(test_akool_polling())
