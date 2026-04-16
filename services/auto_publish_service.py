
import os
import time
import requests
import threading
from config import config
from services.youtube_upload_service import youtube_upload_service
import database as db

class AutoPublishService:
    def __init__(self):
        self.running = False
        self.thread = None
        self.interval = 60 # Check every 60 seconds
        self.auth_server_url = "https://mytube-ashy-seven.vercel.app" if not config.DEBUG else "http://localhost:3000"

    def get_license_key(self):
        if os.path.exists("license.key"):
            with open("license.key", "r") as f:
                return f.read().strip()
        return None

    def start(self):
        if self.running:
            return
        self.running = True
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()
        print("[Auto Publish] Service started.")

    def stop(self):
        self.running = False

    def _run(self):
        while self.running:
            try:
                self._check_and_publish()
            except Exception as e:
                print(f"[Error] AutoPublish error: {e}")
            time.sleep(self.interval)

    def _check_and_publish(self):
        # [NEW] Check if restricted before proceeding
        from services.auth_service import auth_service
        if auth_service.is_restricted():
            return

        user_id = self.get_license_key()
        if not user_id:
            return

        # 1. Get requests from central server
        try:
            res = requests.get(f"{self.auth_server_url}/api/publishing?userId={user_id}", timeout=10)
            if res.status_code != 200:
                return
            
            data = res.json()
            requests_list = data.get('requests', [])
            
            # 2. Filter requests ready for publishing
            publish_queue = [r for r in requests_list if r.get('status') == 'to_be_published']
            
            if not publish_queue:
                return

            print(f"[Info] Found {len(publish_queue)} videos to be published to YouTube.")

            # 3. For each request, update YouTube privacy
            from services.google_drive_service import google_drive_service

            for req in publish_queue:
                req_id = req.get('id')
                metadata = req.get('metadata', {})
                video_id = metadata.get('videoId')
                
                if not video_id:
                    print(f"[Warning] Request {req_id} missing videoId in metadata.")
                    continue

                # Get local project info for token and file path
                token_path = None
                local_video_path = None
                try:
                    # [NEW] Find project by youtube video id
                    p_settings = db.get_project_settings_by_youtube_id(video_id)
                    if p_settings:
                        local_video_path = p_settings.get('video_path')
                        channel_id = p_settings.get('youtube_channel_id')
                        if channel_id:
                            channel = db.get_channel(channel_id)
                            if channel:
                                token_path = channel.get('credentials_path')
                except Exception as db_err:
                    print(f"[DB Error] Failed to find project info for {video_id}: {db_err}")

                try:
                    # A. Update YouTube Privacy
                    youtube_upload_service.update_video_privacy(video_id, "public", token_path=token_path)
                    
                    # B. [NEW] Upload to Google Drive as backup
                    drive_link = None
                    if local_video_path and os.path.exists(local_video_path):
                        print(f"[Drive] Backing up video to Google Drive: {video_id}")
                        drive_link = google_drive_service.upload_video_to_drive(local_video_path, token_path=token_path)
                    
                    # C. Update status to 'published' on central server with Drive Link
                    payload = {
                        "userId": user_id,
                        "requestId": req_id,
                        "status": "published"
                    }
                    if drive_link:
                        payload["driveLink"] = drive_link
                        
                    patch_res = requests.patch(f"{self.auth_server_url}/api/publishing", json=payload, timeout=15)
                    
                    if patch_res.status_code == 200:
                        print(f"[Success] Published {video_id}. Drive Link: {drive_link}")
                    else:
                        print(f"[Warning] Server update failed for {video_id}: {patch_res.text}")
                        
                except Exception as e:
                    err_msg = str(e)
                    print(f"[Error] Failed to publish video {video_id}: {err_msg}")
                    # Report failure to central server
                    try:
                        requests.patch(f"{self.auth_server_url}/api/publishing", json={
                            "userId": user_id,
                            "requestId": req_id,
                            "status": "failed",
                            "error": err_msg
                        }, timeout=5)
                    except: pass

        except Exception:
            # Silence connection errors to central server (port 3000) to keep logs clean
            pass

# Singleton
auto_publish_service = AutoPublishService()
