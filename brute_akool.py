import asyncio
import os
import sys
import httpx
from dotenv import load_dotenv

# Add current dir to sys.path
sys.path.append(os.getcwd())

from services.akool_service import akool_service

load_dotenv()

async def main():
    job_id = "69aa87dfd8ed3511d085fc82" # From last run
    headers = {
        "x-api-key": akool_service.api_key,
        "Content-Type": "application/json"
    }
    
    endpoints = [
        ("GET", f"https://openapi.akool.com/api/v1/content/image/infodetail?_id={job_id}"),
        ("GET", f"https://openapi.akool.com/api/open/v3/content/image/infodetail?_id={job_id}"),
        ("POST", "https://openapi.akool.com/api/open/v3/content/image/resultsByids", {"_ids": job_id}),
        ("POST", "https://openapi.akool.com/api/open/v3/content/image/resultsByIds", {"_ids": job_id}),
        ("POST", "https://openapi.akool.com/api/open/v3/content/image/results", {"_ids": [job_id]}),
        ("POST", "https://openapi.akool.com/api/open/v3/content/image/resultsByids", {"_ids": [job_id]}),
        ("GET", f"https://openapi.akool.com/api/open/v3/content/image/results?_ids={job_id}"),
        ("GET", f"https://openapi.akool.com/api/open/v3/content/image/result?_id={job_id}"),
    ]
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        for method, url, *payload in endpoints:
            try:
                if method == "GET":
                    r = await client.get(url, headers=headers)
                else:
                    r = await client.post(url, json=payload[0], headers=headers)
                print(f"{method} {url}: {r.status_code} -> {r.text[:200]}")
            except: pass

if __name__ == "__main__":
    asyncio.run(main())
