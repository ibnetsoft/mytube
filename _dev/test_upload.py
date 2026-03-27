import asyncio
import httpx
import os

async def test_upload():
    # Create a dummy file
    with open("test_upload.txt", "w") as f:
        f.write("hello akool test")
    
    url = "https://catbox.moe/user/api.php"
    async with httpx.AsyncClient(timeout=30.0) as client:
        with open("test_upload.txt", "rb") as f:
            files = {"fileToUpload": (os.path.basename("test_upload.txt"), f)}
            data = {"reqtype": "fileupload"}
            resp = await client.post(url, data=data, files=files)
            print(f"Status: {resp.status_code}")
            print(f"Result: {resp.text}")

if __name__ == "__main__":
    asyncio.run(test_upload())
