import asyncio
import os
import sys
import httpx
from dotenv import load_dotenv

# Add current dir to sys.path
sys.path.append(os.getcwd())

from services.akool_service import akool_service

load_dotenv()

async def test_akool_v3_final():
    headers = {
        "x-api-key": akool_service.api_key,
        "Content-Type": "application/json"
    }
    
    # 1. Create
    url = "https://openapi.akool.com/api/open/v3/content/image/createbyprompt"
    resp = await httpx.AsyncClient().post(url, json={"prompt": "cat reading a book", "size": "1:1"}, headers=headers)
    job_id = resp.json()["data"]["_id"]
    print(f"JOB ID: {job_id}")
    
    # 2. Poll using infobymodelid
    poll_url = f"https://openapi.akool.com/api/open/v3/content/image/infobymodelid?image_model_id={job_id}"
    for i in range(10):
        await asyncio.sleep(5)
        r = await httpx.AsyncClient().get(poll_url, headers=headers)
        data = r.json()
        print(f"Attempt {i}: {data}")
        if data.get("data", {}).get("image_status") == 3:
            print(f"SUCCESS! URL: {data['data'].get('image') or data['data'].get('url')}")
            return

if __name__ == "__main__":
    asyncio.run(test_akool_v3_final())
