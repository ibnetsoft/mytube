
import os
import requests
import logging
import threading
import time
from datetime import datetime

class AuthService:
    def __init__(self):
        self.license_file = "license.key"
        self.key_file = self.license_file
        # [FORCE] 실서비스(Vercel) 주소를 기본으로 사용 (로컬 개발 시에도 실서버 잔액 확인을 위함)
        custom_url = os.getenv("DASHBOARD_URL")
        base_url = custom_url if custom_url else "https://mytube-ashy-seven.vercel.app"
        
        # 주소가 유효한 엔드포인트를 포함하도록 강제
        self.verify_url = f"{base_url.rstrip('/')}/api/verify"
        self.update_profile_url = f"{base_url.rstrip('/')}/api/user/update-profile"
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
        self._token_balance = self._load_persisted_balance()  # 재시작 시 마지막 잔액 복원
        self._remote_keys_loaded = False
        self.logger = logging.getLogger(__name__)
        self._monitor_thread = None
        self._stop_event = threading.Event()
        self._verify_lock = threading.Lock()

    def _load_persisted_balance(self) -> int:
        """재시작 시 마지막 잔액 복원 — .token_balance 파일 우선, 없으면 로컬 DB에서 조회"""
        try:
            import sqlite3, os
            from config import config
            # 1순위: 빠른 파일 캐시
            balance_file = config.BALANCE_CACHE_PATH
            if os.path.exists(balance_file):
                with open(balance_file) as f:
                    val = int(f.read().strip())
                    if val > 0:
                        return val
            # 2순위: 로컬 DB 최신 balance_after (wingsai.db 사용)
            db_path = config.DB_PATH
            if os.path.exists(db_path):
                conn = sqlite3.connect(db_path)
                # [FIX] 단순히 최신이 아니라, 0보다 큰 마지막 잔액을 가져오도록 수정 (오류로 인한 0원 초기화 방지)
                row = conn.execute(
                    "SELECT balance_after FROM ai_generation_logs WHERE balance_after IS NOT NULL AND balance_after > 0 ORDER BY id DESC LIMIT 1"
                ).fetchone()
                conn.close()
                if row:
                    return int(row[0])
        except Exception:
            pass
        return 0

    def _save_persisted_balance(self, balance: int):
        """잔액을 별도 파일에 저장 (DB 없이도 복원 가능하도록 백업)"""
        try:
            from config import config
            balance_file = config.BALANCE_CACHE_PATH
            os.makedirs(os.path.dirname(balance_file), exist_ok=True)
            with open(balance_file, "w") as f:
                f.write(str(balance))
        except Exception:
            pass

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
        # 동시 호출 방지 — startup + JS sync 동시 실행 시 RECHARGE 중복 감지 차단
        if not self._verify_lock.acquire(blocking=False):
            return self._verified

        try:
            return self._do_verify()
        finally:
            self._verify_lock.release()

    def _do_verify(self, force=False):
        """실제 라이선스 검증 수행"""
        from config import Config
        # DEBUG 모드일 때 license.key가 없거나 'debug'이면 성공으로 처리
        if Config.DEBUG:
            if not os.path.exists(self.key_file):
                self._verified = True
                return True
            try:
                with open(self.key_file, 'r') as f:
                    content = f.read().strip().lower()
                    if content == 'debug':
                        self._verified = True
                        return True
            except:
                pass

        if not os.path.exists(self.key_file):
            self._verified = False
            return False

        try:
            with open(self.license_file, "r") as f:
                license_value = f.read().strip()

            from services.web_admin_client import web_admin_client
            user_id = web_admin_client.resolve_user_id(
                email=self._user_email,
                candidate=license_value,
            )

            if not user_id:
                return False

            hwid = self.get_hwid()
            print(f"[Auth] Attempting verification at: {self.verify_url} (User: {user_id})")
            response = requests.post(
                self.verify_url,
                json={
                    "userId": user_id,
                    "hwid": hwid
                },
                timeout=10,
                proxies={"http": None, "https": None}
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
                        self.logger.warning(f"User {self._user_email} has been restricted by admin.")
                        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] User account restricted by administrator.")
                    else:
                        self._is_restricted = False
                        self._verified = True
                        self.enforce_app_mode()
                        self._last_verified = datetime.now()
                        # [RECHARGE DETECTION] Check if balance increased without recent spent
                        old_balance = self._token_balance
                        remote_balance = data.get("token_balance", 0)
                        
                        # [FIX] If remote balance is 0 but we have local balance, prioritize local
                        # (Prevents zeroing out balance due to sync issues if local DB has valid data)
                        if remote_balance == 0 and old_balance > 0:
                            new_balance = old_balance
                            print(f"[Auth] Remote balance is 0. Falling back to local: {old_balance}")
                        else:
                            new_balance = remote_balance

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
                                        provider="PICADILLY",
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
                        self._save_persisted_balance(new_balance)
                        print(f"[Auth] Sync Success. Balance: {new_balance}")
                        
                        # [FIX] Update Jinja2 Globals for immediate visibility
                        try:
                            from .app_state import get_templates
                            templates = get_templates()
                            if templates:
                                templates.env.globals['membership'] = self._membership
                                templates.env.globals['token_balance'] = self._token_balance
                                templates.env.globals['is_independent'] = self.is_independent()
                                templates.env.globals['user_email'] = self._user_email
                                print(f"[Auth] Updated Template Globals: {self._membership} (Balance: {self._token_balance}, Email: {self._user_email})")
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

    def login_user(self, email: str):
        """직원 이메일로 로그인 세션 및 에셋 폴더 활성화"""
        if self._user_email == email and self._verified:
            return  # 이미 동일한 이메일로 검증 완료됨

        self._user_email = email
        self._verified = True

        # Supabase에서 사용자 프로필 정보 동기화
        try:
            from services.web_admin_client import web_admin_client

            profile = web_admin_client.fetch_profile_by_email(email)
            if profile:
                self._membership = profile.get("membership", "std")
                self._token_balance = profile.get("token_balance", 0)
                self._verified = True
                print(f"[Auth] Logged in user {email}. Membership: {self._membership}, Balance: {self._token_balance}")
                self.enforce_app_mode()

            sys_keys = web_admin_client.fetch_global_api_keys()
            if sys_keys:
                from config import config
                config.load_remote_keys(sys_keys)
                print(f"[Auth] Loaded global API keys from Supabase: {list(sys_keys.keys())}")
        except Exception as e:
            print(f"[Auth] Failed to sync user profile from Supabase on login: {e}")

        # [ISOLATION] C:/Users/사용자/AppData/Local/picadilly/{employee_email}/ 경로로 에셋 저장소 격리
        try:
            from config import config
            # 이메일 특수기호 안전하게 가공
            safe_email = "".join([c if c.isalnum() else "_" for c in email])
            user_dir = os.path.join(config.LOCAL_APP_DATA_DIR, safe_email).replace("\\", "/")
            config.OUTPUT_DIR = os.path.join(user_dir, "output").replace("\\", "/")
            config.LOG_DIR = os.path.join(user_dir, "logs").replace("\\", "/")
            config.ASSETS_DIR = os.path.join(user_dir, "assets").replace("\\", "/")
            config.MEDIA_DIR = config.OUTPUT_DIR
            config.setup_directories()
            print(f"[Auth] Switched output directory for {email} to: {config.OUTPUT_DIR}")

            # Supabase project metadata dirty sync (best-effort, non-blocking)
            try:
                def _sync_dirty_projects_bg():
                    try:
                        from services.project_sync_service import sync_dirty_projects
                        sync_dirty_projects(employee_email=email, limit=20)
                    except Exception as sync_e:
                        print(f"[ProjectSync] Login dirty sync warning: {sync_e}")
                threading.Thread(target=_sync_dirty_projects_bg, daemon=True).start()
            except Exception as sync_e:
                print(f"[ProjectSync] Failed to start login dirty sync: {sync_e}")

            # 템플릿 환경 변수 갱신
            try:
                from .app_state import get_templates
                templates = get_templates()
                if templates:
                    templates.env.globals['membership'] = self._membership
                    templates.env.globals['token_balance'] = self._token_balance
                    templates.env.globals['is_independent'] = self.is_independent()
                    templates.env.globals['user_email'] = self._user_email
            except Exception as e:
                print(f"[Auth] Jinja globals update warning: {e}")
        except Exception as e:
            print(f"[Auth] Directory isolation failed for {email}: {e}")

    def logout_user(self):
        """로그아웃 처리 - 사용자 정보 초기화"""
        self._user_email = ""
        self._user_name = ""
        self._user_nationality = ""
        self._user_contact = ""
        self._membership = "std"
        self._token_balance = 0
        self._verified = False
        
        # 템플릿 환경 변수 초기화
        try:
            from .app_state import get_templates
            templates = get_templates()
            if templates:
                templates.env.globals['membership'] = "std"
                templates.env.globals['token_balance'] = 0
                templates.env.globals['is_independent'] = False
                templates.env.globals['user_email'] = ""
        except Exception as e:
            print(f"[Auth] Jinja globals reset warning: {e}")

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
                timeout=10,
                proxies={"http": None, "https": None}
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
        """작업 시작 전 충분한 토큰이 있는지 확인 (당분간 글로벌 서비스 시작 전까지 시스템 미가동으로 항상 True 반환)"""
        # if self._token_balance < required_amount:
        #     self.logger.warning(f"Insufficient tokens: Available {self._token_balance}, Required {required_amount}")
        #     return False
        return True


    def get_referral_code(self):
        return getattr(self, "_my_referral_code", "")

    def ensure_referral_code_generated(self):
        """첫 렌더링 큐 전송 시 호출되어 추천코드가 없다면 생성 및 Supabase 갱신"""
        current_code = self.get_referral_code()
        if current_code:
            return current_code

        email = self.get_user_email()
        if not email:
            return ""

        import random
        from services.web_admin_client import web_admin_client
        
        new_code = str(random.randint(100000, 999999))
        
        # 1. Update user_metadata in auth.users
        profile = web_admin_client.fetch_profile_by_email(email)
        if profile and profile.get("id"):
            user_id = profile["id"]
            # Fetch current metadata to merge
            # Actually, web_admin_client.update_user_metadata replaces it or merges it depending on how supabase does it.
            # Supabase auth.admin.updateUser merges user_metadata.
            web_admin_client.update_user_metadata(user_id, {"my_referral_code": new_code})

            # 2. Update profiles table if it also has my_referral_code column
            web_admin_client.supabase_patch("profiles", {"my_referral_code": new_code}, params={"id": f"eq.{user_id}"})
            
        self._my_referral_code = new_code
        self.logger.info(f"Generated and assigned new referral code: {new_code}")
        return new_code

    def get_or_create_wallet_info(self):
        import json
        import database as db
        
        from config import config
        wallet_file = config.WALLET_KEY_PATH
        wallet_data = {}
        
        # 1. Try to load existing
        if os.path.exists(wallet_file):
            try:
                with open(wallet_file, "r") as f:
                    wallet_data = json.load(f)
            except Exception as e:
                self.logger.error(f"Error loading wallet info: {e}")
        
        # 2. Create new if not exists
        if not wallet_data or "address" not in wallet_data:
            try:
                from services.crypto_service import generate_bep20_wallet
                wallet_data = generate_bep20_wallet()
                with open(wallet_file, "w") as f:
                    json.dump(wallet_data, f)
            except Exception as e:
                self.logger.error(f"Error generating wallet: {e}")
                wallet_data = {"address": ""}
                
        return wallet_data

    def enforce_app_mode(self):
        """멤버십 등급에 따라 강제로 앱 모드를 세팅하여 무단 전환을 막음"""
        import database as db
        allowed_mode = None
        if self._membership == "std":
            allowed_mode = "longform"
        elif self._membership == "music":
            allowed_mode = "longform_music"
        elif self._membership == "shorts":
            allowed_mode = "shorts"
        elif self._membership == "commerce":
            allowed_mode = "commerce"
        
        if allowed_mode:
            current_mode = db.get_global_setting("app_mode", "longform")
            if current_mode != allowed_mode:
                db.update_global_setting("app_mode", allowed_mode)
                print(f"[Auth] Enforced app_mode to '{allowed_mode}' for membership '{self._membership}'")

        # 3. Calculate actual balance
        total_payout_krw = 0
        total_withdrawn_usdt = 0
        
        try:
            if self._user_email:
                history = db.get_worker_project_history(self._user_email)
                for h in history:
                    total_payout_krw += (h.get("payout_amount") or 0)
                    
                withdrawals = db.get_worker_withdrawals(self._user_email)
                for w in withdrawals:
                    total_withdrawn_usdt += (w.get("amount") or 0)
        except Exception as e:
            self.logger.error(f"Error calculating balance: {e}")
            
        total_generated_usdt = round(total_payout_krw / 1400.0, 2)
        current_balance = round(total_generated_usdt - total_withdrawn_usdt, 2)
        if current_balance < 0:
            current_balance = 0
            
        # [MIGRATION] Sync actual balance to Supabase in the background
        if self._user_email:
            try:
                import threading
                from services.web_admin_client import web_admin_client
                address = wallet_data.get("address", "")
                threading.Thread(target=web_admin_client.sync_wallet_info, args=(self._user_email, current_balance, address), daemon=True).start()
            except Exception as e:
                self.logger.error(f"Error syncing balance to Supabase: {e}")
                
        return {
            "address": wallet_data.get("address", ""),
            "balance": current_balance,
            "saved_external_wallet": wallet_data.get("saved_external_wallet", "")
        }

auth_service = AuthService()
