
import os
import requests
import logging
import threading
import time
from datetime import datetime

class AuthService:
    def __init__(self):
        self.license_file = "license.key"
        self.verify_url = "https://mytube-ashy-seven.vercel.app/api/verify"
        self._membership = "standard" # Default
        self._user_email = ""
        self._youtube_channel = ""
        self._youtube_handle = ""
        self._verified = False
        self._last_verified = None
        self._is_restricted = False
        self._remote_keys_loaded = False   # 이번 세션에서 원격 키를 받았는지
        self.logger = logging.getLogger(__name__)
        self._monitor_thread = None
        self._stop_event = threading.Event()

    def get_hwid(self):
        """Retrieve unique Hardware ID for Windows (UUID) or MAC address fallback"""
        import subprocess
        try:
            # Windows CMD to get UUID
            result = subprocess.check_output('wmic csproduct get uuid', shell=True).decode()
            hwid = result.split('\n')[1].strip()
            if not hwid or 'UUID' in hwid:
                raise Exception("Invalid UUID format")
            return hwid
        except Exception:
            try:
                # Fallback: MAC Address-based ID
                import uuid
                return ':'.join(['{:02x}'.format((uuid.getnode() >> ele) & 0xff)
                             for ele in range(0, 8*6, 8)][::-1])
            except:
                return "UNKNOWN_HWID"

    def verify_license(self):
        if not os.path.exists(self.license_file):
            self.logger.warning("License file not found")
            self._verified = False
            return False

        try:
            with open(self.license_file, "r") as f:
                user_id = f.read().strip()

            if not user_id:
                return False

            hwid = self.get_hwid()
            
            response = requests.post(
                self.verify_url,
                json={
                    "userId": user_id,
                    "hwid": hwid
                },
                timeout=10
            )

            if response.status_code == 200:
                data = response.json()
                if data.get("success"):
                    self._membership = data.get("membership", "standard")
                    self._user_email = data.get("email", "")
                    self._youtube_channel = data.get("youtube_channel", "")
                    self._youtube_handle = data.get("youtube_handle", "")
                    
                    # [NEW] Check for restriction from admin
                    if data.get("status") == "restricted":
                        self._is_restricted = True
                        self._verified = False
                        self.logger.warning(f"ACCESS RESTRICTED BY ADMIN for {user_id}")
                    else:
                        self._is_restricted = False
                        self._verified = True
                        self._last_verified = datetime.now()
                    
                    # Supabase 원격 API 키 → 메모리 전용 로드 (로컬 저장 없음)
                    api_keys = data.get("api_keys", {})
                    if api_keys and isinstance(api_keys, dict):
                        try:
                            from config import Config
                            loaded = Config.load_remote_keys(api_keys)
                            self._remote_keys_loaded = bool(loaded)
                        except Exception as ke:
                            self.logger.warning(f"원격 키 로드 실패 (무시): {ke}")

                    return True if self._verified else False
            
            self._verified = False
            self.logger.error(f"License verification failed for {user_id}/{hwid}: {response.text}")
            return False

        except Exception as e:
            self.logger.error(f"Error during license verification: {e}")
            return False

    def start_monitoring(self):
        """Start background thread to re-verify license every 10 minutes (Sync with Vercel Admin)"""
        if self._monitor_thread and self._monitor_thread.is_alive():
            return

        def _monitor_loop():
            while not self._stop_event.is_set():
                # Wait 10 minutes between checks
                for _ in range(600): # Check stop event every second
                    if self._stop_event.is_set(): return
                    time.sleep(1)
                
                self.logger.info("Performing periodic license re-verification...")
                self.verify_license()

        self._monitor_thread = threading.Thread(target=_monitor_loop, daemon=True)
        self._monitor_thread.start()
        self.logger.info("Admin Monitoring Service started (10m interval)")

    def is_verified(self):
        return self._verified and not self._is_restricted

    def is_restricted(self):
        return self._is_restricted

    def is_independent(self):
        return self._membership == "independent"

    def get_membership(self):
        return self._membership

    def get_user_email(self):
        return self._user_email

    def get_youtube_channel(self):
        return self._youtube_channel

    def get_youtube_handle(self):
        return self._youtube_handle

    def remote_keys_loaded(self):
        """이번 세션에서 Supabase 원격 키를 성공적으로 받았는지 여부"""
        return self._remote_keys_loaded

auth_service = AuthService()
