
import os
import requests
import logging

class StorageService:
    def __init__(self):
        self.logger = logging.getLogger("StorageService")
        # [MOD] Use localhost for development if auth-web is running locally
        self.auth_base_url = "http://localhost:3000" # "https://mytube-ashy-seven.vercel.app"

    def upload_video_to_cloud(self, user_id, local_file_path):
        """
        1. Get Signed URL from Central Server
        2. Upload binary file to Signed URL
        3. Return Public URL
        """
        if not os.path.exists(local_file_path):
            self.logger.error(f"File not found: {local_file_path}")
            return None

        file_name = os.path.basename(local_file_path)
        
        try:
            # Step 1: Request Signed URL
            self.logger.info(f"Requesting signed URL for {file_name}...")
            res = requests.post(
                f"{self.auth_base_url}/api/publishing/presigned-url",
                json={
                    "userId": user_id,
                    "fileName": file_name
                },
                timeout=10
            )
            
            if res.status_code != 200:
                self.logger.error(f"Failed to get signed URL: {res.text}")
                return None
                
            data = res.json()
            upload_url = data.get("uploadUrl")
            file_path = data.get("path") # the cloud path e.g. userId/time_name.mp4

            if not upload_url:
                self.logger.error("No uploadUrl in response")
                return None

            # Step 2: Upload File
            self.logger.info(f"Uploading to Cloud... (Size: {os.path.getsize(local_file_path) / 1024 / 1024:.2f} MB)")
            with open(local_file_path, 'rb') as f:
                upload_res = requests.put(
                    upload_url,
                    data=f,
                    headers={'Content-Type': 'video/mp4'}, # Basic assumption
                    timeout=600 # 10 mins for large videos
                )

            if upload_res.status_code not in [200, 201]:
                self.logger.error(f"Cloud Upload Failed: {upload_res.status_code} {upload_res.text}")
                return None

            # Step 3: Get Public URL (Supabase pattern)
            # Pattern: {supabase_url}/storage/v1/object/public/videos/{filePath}
            # We can get supabase_url from the response or hardcode if we know it.
            # However, for simplicity, we let the Central Server handle the submission of this path.
            self.logger.info("Cloud Upload Success!")
            return file_path

        except Exception as e:
            self.logger.error(f"Storage Service Error: {e}")
            return None

storage_service = StorageService()
