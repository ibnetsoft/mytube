
import os
import requests
import logging
import threading
import time
from datetime import datetime

class AuthService:
    def __init__(self):
        self.license_file = "license.key"
        # 전역 환경변수 또는 프로덕션 URL 사용
        base_url = os.getenv("DASHBOARD_URL", "https://mytube-ashy-seven.vercel.app")
        
        # 로컬 개발 환경 감지 (auth-web 폴더 존재 시 localhost 사용 가능성 높음)
        if os.path.exists("auth-web") and os.getenv("DEBUG") == "true":
            try:
                import requests as _req
                check = _req.get("http://localhost:3000/api/health", timeout=0.5)
                if check.status_code == 200:
                    base_url = "http://localhost:3000"
            except:
                pass

        self.verify_url = f"{base_url}/api/verify"
        self.update_profile_url = f"{base_url}/api/user/update-profile"
        self._membership = "std" # Default
        self._user_email = ""
        self._user_name = ""
        self._user_nationality = ""
        self._user_contact = ""
        self._youtube_channel = ""
        self._youtube_handle = ""
        self._verified = False
        self._last_verified = None
        self._is_restricted = False
        self._token_balance = 0
        self._remote_keys_loaded = False 
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
                    raw = data.get("membership", "std")
                    # 서버 값 정규화: "standard" → "std", "independent" → "pro"
                    _norm = {"standard": "std", "independent": "pro"}
                    self._membership = _norm.get(raw, raw)
                    self._user_email = data.get("email", "")
                    self._user_name = data.get("full_name", "")
                    self._user_nationality = data.get("nationality", "")
                    self._user_contact = data.get("contact", "")
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
                        # [RECHARGE DETECTION] Check if balance increased without recent spent
                        old_balance = self._token_balance
                        new_balance = data.get("token_balance", 0)
                        
                        if self._verified and new_balance > old_balance:
                            recharge_amount = new_balance - old_balance
                            # If increased significantly, record a RECHARGE log
                            if recharge_amount >= 10: # Minimum 10 units to be considered a recharge
                                try:
                                    from database import add_ai_log
                                    add_ai_log(
                                        project_id=None,
                                        task_type="RECHARGE",
                                        model_id="BILLING",
                                        provider="PICADIRI",
                                        status="success",
                                        prompt_summary=f"Token recharge: +{recharge_amount:,}",
                                        input_tokens=recharge_amount, # Show recharge amount in tokens col
                                        output_tokens=0,
                                        balance_after=new_balance
                                    )
                                    print(f"[Auth] Recharge detected and logged: +{recharge_amount}")
                                except Exception as le:
                                    print(f"[Auth] Failed to log recharge: {le}")

                        self._token_balance = new_balance
                        
                        # [FIX] Update Jinja2 Globals for immediate visibility
                        try:
                            from .app_state import get_templates
                            templates = get_templates()
                            if templates:
                                templates.env.globals['membership'] = self._membership
                                templates.env.globals['token_balance'] = self._token_balance
                                templates.env.globals['is_independent'] = self.is_independent()
                                print(f"[Auth] Updated Template Globals: {self._membership} (Balance: {self._token_balance})")
                        except Exception as e:
                            print(f"[Auth] Template sync error: {e}")
                    
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
                # Wait 30 seconds between checks (faster sync for testing)
                for _ in range(30): # Check stop event every second
                    if self._stop_event.is_set(): return
                    time.sleep(1)
                
                self.logger.info("Performing periodic license re-verification...")
                self.verify_license()

        self._monitor_thread = threading.Thread(target=_monitor_loop, daemon=True)
        self._monitor_thread.start()
        self.logger.info("Admin Monitoring Service started (30s interval)")

    def is_verified(self):
        return self._verified and not self._is_restricted

    def is_restricted(self):
        return self._is_restricted

    def sync_profile(self, name: str, nationality: str, contact: str):
        """Sync local user profile info to the SaaS server"""
        if not os.path.exists(self.license_file):
            return False

        try:
            with open(self.license_file, "r") as f:
                user_id = f.read().strip()

            if not user_id:
                return False

            response = requests.post(
                self.update_profile_url,
                json={
                    "userId": user_id,
                    "full_name": name,
                    "nationality": nationality,
                    "contact": contact
                },
                timeout=10
            )
            
            if response.status_code == 200:
                print(f"[Sync] SaaS Profile Sync Success: {name}")
                # Update local cache too
                self._user_name = name
                self._user_nationality = nationality
                self._user_contact = contact
                return True
            else:
                print(f"[Sync] SaaS Profile Sync Failed ({response.status_code}): {response.text}")
                return False
        except Exception as e:
            print(f"[Sync] Error syncing profile to SaaS: {e}")
            self.logger.error(f"Error syncing profile to SaaS: {e}")
            return False

    def is_independent(self):
        return self._membership in ("independent", "pro")

    def get_membership(self):
        return self._membership

    def get_user_email(self):
        return self._user_email

    def get_youtube_channel(self):
        return self._youtube_channel

    def get_youtube_handle(self):
        return self._youtube_handle

    def get_user_name(self):
        return self._user_name

    def get_user_nationality(self):
        return self._user_nationality

    def get_user_contact(self):
        return self._user_contact

    def remote_keys_loaded(self):
        """이번 세션에서 Supabase 원격 키를 성공적으로 받았는지 여부"""
        return self._remote_keys_loaded

    def get_token_balance(self):
        return self._token_balance

    def check_credits(self, required_amount: int = 1000):
        """작업 시작 전 충분한 토큰이 있는지 확인"""
        if self._token_balance < required_amount:
            self.logger.warning(f"Insufficient tokens: Available {self._token_balance}, Required {required_amount}")
            return False
        return True

auth_service = AuthService()
