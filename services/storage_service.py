
import os
import requests
import logging
from services.web_admin_client import web_admin_client

class StorageService:
    def __init__(self):
        self.logger = logging.getLogger("StorageService")
        self.auth_base_url = web_admin_client.dashboard_url

    def upload_video_to_cloud(self, user_id, local_file_path):
        """
        1. Get Signed URL from Central Server
        2. Upload binary file to Signed URL
        3. Return Public URL
        """
        if not os.path.exists(local_file_path):
            self.logger.error(f"File not found: {local_file_path}")
            return None

        # [AIR-0225B] /api/publishing/presigned-url은 이제 email + HMAC
        # session_token을 검증한다(평문 userId 신뢰 구멍 제거). 서버가 세션
        # email로 user_id를 해석하므로, 서비스롤이 필요한 resolve_user_id에
        # 더 이상 의존하지 않는다(패키징 앱에서 깨지던 경로).
        try:
            from services.auth_service import auth_service
            email = auth_service.get_user_email()
            session_token = auth_service.get_session_token()
        except Exception:
            email = ""
            session_token = ""
        if not email or not session_token:
            self.logger.error("Cloud upload requires an active login session (email/session_token).")
            return None

        file_name = os.path.basename(local_file_path)

        try:
            # Step 1: Request Signed URL
            self.logger.info(f"Requesting signed URL for {file_name}...")
            res = requests.post(
                f"{self.auth_base_url}/api/publishing/presigned-url",
                json={
                    "email": email,
                    "session_token": session_token,
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
