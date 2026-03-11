import asyncio
import os
import sys
import httpx
from dotenv import load_dotenv

# Add current dir to sys.path
sys.path.append(os.getcwd())

from services.akool_service import akool_service

load_dotenv()

async def test_endpoint(job_id, url_template, method="GET", json_payload=None):
    headers = {
        "x-api-key": akool_service.api_key,
        "Content-Type": "application/json"
    }
    url = url_template.replace("{job_id}", job_id)
    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            if method == "GET":
                resp = await client.get(url, headers=headers)
            else:
                resp = await client.post(url, json=json_payload, headers=headers)
            print(f"URL: {url}, Status: {resp.status_code}, Body: {resp.text}")
        except Exception as e:
            print(f"ERROR for {url}: {e}")

async def main():
    # Use the job ID from previous run if possible, or create a new one
    job_id = "69aa8726d8ed3511d085fa86" # From previous log
    
    print("--- Testing Akool Status Endpoints ---")
    
    # Try various patterns
    await test_endpoint(job_id, "https://openapi.akool.com/api/open/v3/content/image/infodetail?_id={job_id}")
    await test_endpoint(job_id, "https://openapi.akool.com/api/open/v3/content/image/resultsByids", method="POST", json_payload={"_ids": job_id})
    await test_endpoint(job_id, "https://openapi.akool.com/api/open/v3/content/image/resultsByIds", method="POST", json_payload={"_ids": job_id})
    await test_endpoint(job_id, "https://openapi.akool.com/api/open/v3/content/image/results?_ids={job_id}")

if __name__ == "__main__":
    asyncio.run(main())
