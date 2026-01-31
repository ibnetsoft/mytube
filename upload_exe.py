
import httpx
import os

supabase_url = "https://giorysjpgxzdypbmxwmx.supabase.co"
supabase_key = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Imdpb3J5c2pwZ3h6ZHlwYm14d214Iiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc2OTg0MTc3OSwiZXhwIjoyMDg1NDE3Nzc5fQ.bVpsP4y3NS1yXFpe0YZjKWCz_zHYOiXsEmm_GL3mXHw"
file_path = r"c:\Users\kimse\Downloads\유튜브소재발굴기\롱폼생성기\dist\MyTubeStudio.exe"

headers = {
    "Authorization": f"Bearer {supabase_key}",
}

print(f"Uploading {file_path} to Supabase Storage...")

# 1. Ensure bucket exists
try:
    print("Checking/Creating 'downloads' bucket...")
    httpx.post(
        f"{supabase_url}/storage/v1/bucket", 
        headers=headers, 
        json={"id": "downloads", "name": "downloads", "public": True},
        timeout=10.0
    )
except Exception as e:
    print(f"Bucket might already exist or error: {e}")

# 2. Upload file
filename = "MyTubeStudio_v2.0.1.exe"
upload_url = f"{supabase_url}/storage/v1/object/downloads/{filename}"

try:
    with open(file_path, "rb") as f:
        # We need a large timeout for 150MB
        res = httpx.post(
            upload_url,
            headers={**headers, "Content-Type": "application/octet-stream", "x-upsert": "true"},
            content=f,
            timeout=600.0 
        )
        if res.status_code == 200:
            public_url = f"{supabase_url}/storage/v1/object/public/downloads/{filename}"
            print(f"\n✅ Upload Successful!")
            print(f"Public URL: {public_url}")
        else:
            print(f"\n❌ Upload Failed: {res.status_code}")
            print(res.text)
except Exception as e:
    print(f"\n❌ Error during upload: {e}")
