import asyncio
import os
import sys
import httpx
from dotenv import load_dotenv

# Add current dir to sys.path
sys.path.append(os.getcwd())

from services.akool_service import akool_service

load_dotenv()

async def debug_akool_comprehensive():
    headers = {
        "x-api-key": akool_service.api_key,
        "Content-Type": "application/json"
    }
    
    # 1. Create Job
    create_url = "https://openapi.akool.com/api/open/v3/content/image/createbyprompt"
    payload = {"prompt": "a beautiful landscape", "size": "1:1"}
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(create_url, json=payload, headers=headers)
        res = resp.json()
        print(f"CREATE Response: {res}")
        if res.get("code") != 1000: return
        
        job_id = res["data"]["_id"]
        print(f"NEW JOB ID: {job_id}")
        
        # Wait a bit
        await asyncio.sleep(5)
        
        # 2. Try polling with different formats
        poll_urls = [
            ("https://openapi.akool.com/api/open/v3/content/image/resultsByids", {"_ids": job_id}),
            ("https://openapi.akool.com/api/open/v3/content/image/resultsByids", {"_ids": [job_id]}),
            ("https://openapi.akool.com/api/open/v3/content/image/infodetail?_id=" + job_id, None)
        ]
        
        for url, payload in poll_urls:
            print(f"--- Testing: {url} with {payload} ---")
            if payload:
                r = await client.post(url, json=payload, headers=headers)
            else:
                r = await client.get(url, headers=headers)
            print(f"Status: {r.status_code}, Body: {r.text}")

if __name__ == "__main__":
    asyncio.run(debug_akool_comprehensive())
