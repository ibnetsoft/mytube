
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
        print("🚀 Auto Publish Service started.")

    def stop(self):
        self.running = False

    def _run(self):
        while self.running:
            try:
                self._check_and_publish()
            except Exception as e:
                print(f"❌ AutoPublish error: {e}")
            time.sleep(self.interval)

    def _check_and_publish(self):
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

            print(f"🔔 Found {len(publish_queue)} videos to be published to YouTube.")

            # 3. For each request, update YouTube privacy
            for req in publish_queue:
                req_id = req.get('id')
                metadata = req.get('metadata', {})
                video_id = metadata.get('videoId')
                
                if not video_id:
                    print(f"⚠️ Request {req_id} missing videoId in metadata.")
                    continue

                # [NEW] 채널 정보 조회하여 토큰 경로 결정 (main.py의 로직과 동일하게)
                token_path = None
                try:
                    channels = db.get_all_channels()
                    if channels:
                        cand_path = channels[0].get('credentials_path')
                        if cand_path and os.path.exists(cand_path):
                            token_path = cand_path
                except:
                    pass

                try:
                    # Update YouTube Privacy
                    youtube_upload_service.update_video_privacy(video_id, "public", token_path=token_path)
                    
                    # Update status to 'published' on central server
                    patch_res = requests.patch(f"{self.auth_server_url}/api/publishing", json={
                        "userId": user_id,
                        "requestId": req_id,
                        "status": "published"
                    }, timeout=10)
                    
                    if patch_res.status_code == 200:
                        print(f"✅ Video {video_id} is now PUBLIC and marked as published.")
                    else:
                        print(f"⚠️ Failed to update status on server for {video_id}: {patch_res.text}")
                        
                except Exception as e:
                    print(f"❌ Failed to publish video {video_id}: {e}")

        except Exception as e:
            print(f"❌ Failed to connect to Central Server: {e}")

# Singleton
auto_publish_service = AutoPublishService()
