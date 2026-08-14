import os
import re
import secrets
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests
from dotenv import load_dotenv


def _load_packaged_env():
    candidates = []
    if getattr(sys, "frozen", False):
        candidates.append(Path(getattr(sys, "_MEIPASS", "")) / ".env")
        candidates.append(Path(sys.executable).resolve().parent / ".env")
        candidates.append(Path(sys.executable).resolve().parent / "_internal" / ".env")
    candidates.append(Path.cwd() / ".env")
    candidates.append(Path(__file__).resolve().parents[1] / ".env")
    for path in candidates:
        try:
            if path and path.exists():
                load_dotenv(path, override=False)
        except Exception:
            pass


load_dotenv()
_load_packaged_env()


UUID_RE = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)


def _human_error(value: Any, fallback: str) -> str:
    if isinstance(value, str) and value.strip():
        return value.strip()
    if isinstance(value, dict):
        for key in ("message", "error", "details", "hint", "code", "status"):
            text = _human_error(value.get(key), "")
            if text:
                return text
        parts = [_human_error(item, "") for item in value.values()]
        parts = [item for item in parts if item]
        if parts:
            return " / ".join(parts)
    if isinstance(value, list):
        parts = [_human_error(item, "") for item in value]
        parts = [item for item in parts if item]
        if parts:
            return " / ".join(parts)
    return fallback


class WebAdminClient:
    """Small wrapper for Vercel web-admin and Supabase REST integration."""

    KEY_MAP = {
        "sys_api_gemini": "GEMINI_API_KEY",
        "sys_api_youtube": "YOUTUBE_API_KEY",
        "sys_api_youtube_keys": "YOUTUBE_API_KEYS",
        "sys_api_claude": "CLAUDE_API_KEY",
        "sys_api_deepseek": "DEEPSEEK_API_KEY",
        "sys_api_deepseek_base_url": "DEEPSEEK_BASE_URL",
        "sys_api_glm": "GLM_API_KEY",
        "sys_api_glm_base_url": "GLM_BASE_URL",
        "sys_api_elevenlabs": "ELEVENLABS_API_KEY",
        "sys_api_suno": "SUNO_API_KEY",
        "sys_api_suno_base_url": "SUNO_API_BASE_URL",
        "sys_api_music_provider": "MUSIC_PROVIDER",
        "sys_api_music_gemini_model": "MUSIC_GEMINI_MODEL",
        "sys_api_music_gemini_base_url": "MUSIC_GEMINI_BASE_URL",
        "sys_api_music_gemini_project_id": "MUSIC_GEMINI_PROJECT_ID",
        "sys_api_music_gemini_location": "MUSIC_GEMINI_LOCATION",
        "sys_api_topview": "TOPVIEW_API_KEY",
        "sys_api_topview_uid": "TOPVIEW_UID",
        "sys_api_remote_render_drive_folder_id": "REMOTE_RENDER_DRIVE_FOLDER_ID",
        "sys_api_remote_render_google_token_path": "REMOTE_RENDER_GOOGLE_TOKEN_PATH",
        "sys_api_longform_min_duration_minutes": "LONGFORM_MIN_DURATION_MINUTES",
        "sys_api_longform_base_payout": "LONGFORM_BASE_PAYOUT",
        "sys_api_longform_extra_minute_payout": "LONGFORM_EXTRA_MINUTE_PAYOUT",
        "sys_api_longform_duration_lock_enabled": "LONGFORM_DURATION_LOCK_ENABLED",
        "sys_api_topic_generation_model": "TOPIC_GENERATION_MODEL",
        "sys_api_title_generation_model": "TITLE_GENERATION_MODEL",
        "sys_api_script_planning_model": "SCRIPT_PLANNING_MODEL",
        "sys_api_script_generation_model": "SCRIPT_GENERATION_MODEL",
        "sys_api_image_prompt_model": "IMAGE_PROMPT_MODEL",
        "sys_api_translation_model": "TRANSLATION_MODEL",
        "sys_api_image_generation_model": "IMAGE_GENERATION_MODEL",
        "sys_api_video_generation_model": "VIDEO_GENERATION_MODEL",
        "sys_api_drive_render_queue_path": "DRIVE_RENDER_QUEUE_PATH",
        "sys_api_use_external_render": "USE_EXTERNAL_RENDER",
        "latest_app_version": "LATEST_APP_VERSION",
        "latest_app_url": "LATEST_APP_URL",
    }

    def __init__(self):
        self.timeout = 10

    @property
    def dashboard_url(self) -> str:
        custom_url = os.getenv("DASHBOARD_URL")
        if custom_url:
            return custom_url.rstrip("/")
        return "https://mytube-ashy-seven.vercel.app"

    @property
    def supabase_url(self) -> str:
        return (os.getenv("NEXT_PUBLIC_SUPABASE_URL") or "").rstrip("/")

    @property
    def supabase_key(self) -> str:
        return os.getenv("SUPABASE_SERVICE_ROLE_KEY") or ""

    def has_supabase(self) -> bool:
        return bool(self.supabase_url and self.supabase_key)

    def headers(self, content_type: bool = False) -> Dict[str, str]:
        headers = {
            "apikey": self.supabase_key,
            "Authorization": f"Bearer {self.supabase_key}",
        }
        if content_type:
            headers["Content-Type"] = "application/json"
        return headers

    def dashboard_headers(self, content_type: bool = False) -> Dict[str, str]:
        headers: Dict[str, str] = {}
        bypass_secret = os.getenv("VERCEL_AUTOMATION_BYPASS_SECRET", "").strip()
        if bypass_secret:
            headers["x-vercel-protection-bypass"] = bypass_secret
        if content_type:
            headers["Content-Type"] = "application/json"
        return headers

    def _disable_warnings(self):
        try:
            import urllib3

            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        except Exception:
            pass

    def supabase_get(self, table: str, *, params: Optional[Dict[str, Any]] = None, timeout: Optional[int] = None):
        if not self.has_supabase():
            return None
        self._disable_warnings()
        return requests.get(
            f"{self.supabase_url}/rest/v1/{table}",
            headers=self.headers(),
            params=params or {},
            timeout=timeout or self.timeout,
            verify=False,
            proxies={"http": None, "https": None},
        )

    def supabase_post(
        self,
        table: str,
        payload: Dict[str, Any],
        *,
        timeout: Optional[int] = None,
        return_representation: bool = False,
    ):
        if not self.has_supabase():
            return None
        self._disable_warnings()
        headers = self.headers(content_type=True)
        if return_representation:
            headers["Prefer"] = "return=representation"
        return requests.post(
            f"{self.supabase_url}/rest/v1/{table}",
            headers=headers,
            json=payload,
            timeout=timeout or self.timeout,
            verify=False,
            proxies={"http": None, "https": None},
        )

    def rpc(
        self,
        function_name: str,
        payload: Optional[Dict[str, Any]] = None,
        *,
        timeout: Optional[int] = None,
    ):
        if not self.has_supabase() or not function_name:
            return None
        self._disable_warnings()
        return requests.post(
            f"{self.supabase_url}/rest/v1/rpc/{function_name}",
            headers=self.headers(content_type=True),
            json=payload or {},
            timeout=timeout or self.timeout,
            verify=False,
            proxies={"http": None, "https": None},
        )

    def supabase_patch(
        self,
        table: str,
        payload: Dict[str, Any],
        *,
        params: Optional[Dict[str, Any]] = None,
        timeout: Optional[int] = None,
    ):
        if not self.has_supabase():
            return None
        self._disable_warnings()
        headers = self.headers(content_type=True)
        headers["Prefer"] = "return=representation"
        return requests.patch(
            f"{self.supabase_url}/rest/v1/{table}",
            headers=headers,
            params=params or {},
            json=payload,
            timeout=timeout or self.timeout,
            verify=False,
            proxies={"http": None, "https": None},
        )

    def upsert_by_key(
        self,
        table: str,
        key: str,
        key_value: Any,
        payload: Dict[str, Any],
        *,
        timeout: Optional[int] = None,
    ) -> bool:
        """Patch by key, insert if no row exists. Best-effort Supabase REST upsert."""
        if not self.has_supabase() or key_value in (None, ""):
            return False

        response = self.supabase_patch(table, payload, params={key: f"eq.{key_value}"}, timeout=timeout)
        if response is None:
            return False
        if response.status_code >= 400:
            print(f"[WebAdmin] {table} patch failed: HTTP {response.status_code} {response.text[:300]}")
            return False

        try:
            rows = response.json() or []
        except Exception:
            rows = []
        if rows:
            return True

        create_response = self.supabase_post(table, payload, timeout=timeout)
        if create_response is None:
            return False
        if create_response.status_code >= 400:
            print(f"[WebAdmin] {table} insert failed: HTTP {create_response.status_code} {create_response.text[:300]}")
            return False
        return True

    def create_auth_user(self, *, email: str, metadata: Dict[str, Any]) -> Optional[str]:
        if not self.has_supabase():
            return None
        self._disable_warnings()
        response = requests.post(
            f"{self.supabase_url}/auth/v1/admin/users",
            headers=self.headers(content_type=True),
            json={
                "email": email,
                "password": secrets.token_urlsafe(24),
                "email_confirm": True,
                "user_metadata": metadata,
            },
            timeout=self.timeout,
            verify=False,
            proxies={"http": None, "https": None},
        )
        if response.status_code not in (200, 201):
            print(f"[WebAdmin] auth user create failed: HTTP {response.status_code} {response.text[:300]}")
            return None
        return (response.json() or {}).get("id")

    def fetch_global_setting(self, key: str, default: Any = None) -> Any:
        if not self.has_supabase():
            return default
        try:
            response = self.supabase_get(
                "global_settings",
                params={"select": "value", "key": f"eq.{key}"},
            )
            if response and response.status_code == 200:
                rows = response.json()
                if rows:
                    return rows[0].get("value")
        except Exception as e:
            print(f"[WebAdmin] Failed to fetch global setting {key}: {e}")
        return default

    def validate_referral_code(self, code: str) -> bool:
        """Check if the referral code exists in profiles."""
        if not self.has_supabase() or not code:
            return False
        try:
            response = self.supabase_get(
                "profiles",
                params={"select": "id", "referral_code": f"eq.{code.strip()}", "limit": "1"},
            )
            if response and response.status_code == 200:
                rows = response.json()
                if rows:
                    return True
        except Exception as e:
            print(f"[WebAdmin] Failed to validate referral code {code}: {e}")
        return False

    def submit_worker_registration(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        email = (payload.get("email") or "").strip().lower()
        if not email:
            return {"success": False, "error": "email is required"}

        existing = self.fetch_profile_by_email(email)
        if existing and str(existing.get("is_approved")).lower() in ("true", "1", "yes"):
            return {"success": False, "error": "이미 승인된 이메일입니다. 로그인 화면에서 접속해주세요."}

        profile_id = (existing or {}).get("id")
        my_referral_code = payload.get("my_referral_code") or ""
        metadata = {
            "full_name": payload.get("full_name") or "",
            "contact": payload.get("contact") or "",
            "nationality": payload.get("nationality") or "",
            "signup_status": "pending",
            "signup_source": "desktop_client",
            "my_referral_code": my_referral_code,
            "referred_by_code": payload.get("referred_by_code") or "",
            "referred_by_id": payload.get("referred_by_id") or "",
            "preferred_category_ids": payload.get("preferred_category_ids") or [],
            "preferred_category_names": payload.get("preferred_category_names") or [],
            "preferred_video_length": payload.get("preferred_video_length") or "",
        }
        if not profile_id:
            profile_id = self.create_auth_user(email=email, metadata=metadata)
        if not profile_id:
            return {"success": False, "error": "가입 신청 계정을 생성하지 못했습니다. 관리자에게 문의해주세요."}

        profile_payload = {
            "email": email,
            "full_name": metadata["full_name"],
            "contact": metadata["contact"],
            "nationality": metadata["nationality"],
            "is_approved": False,
            "signup_status": "pending",
            "signup_source": "desktop_client",
            "terms_accepted_at": payload.get("terms_accepted_at"),
            "privacy_accepted_at": payload.get("privacy_accepted_at"),
            "pin_code": payload.get("password") or (existing or {}).get("pin_code") or "1234",
            "membership": (existing or {}).get("membership") or "std",
            "preferred_category_ids": payload.get("preferred_category_ids") or [],
            "preferred_category_names": payload.get("preferred_category_names") or [],
            "preferred_video_length": payload.get("preferred_video_length") or "",
        }

        response = self.supabase_patch("profiles", profile_payload, params={"id": f"eq.{profile_id}"}, timeout=8)
        if response is None:
            return {"success": False, "error": "서버 DB 연동 설정이 누락되었습니다."}
        if response.status_code >= 400:
            print(f"[WebAdmin] profile registration patch failed: HTTP {response.status_code} {response.text[:300]}")
            return {"success": False, "error": "가입 신청 정보 저장에 실패했습니다. profiles 컬럼 마이그레이션이 필요할 수 있습니다."}
        try:
            updated_rows = response.json() or []
        except Exception:
            updated_rows = []
        if not updated_rows:
            create_response = self.supabase_post("profiles", {"id": profile_id, **profile_payload}, timeout=8)
            if create_response is not None and create_response.status_code >= 400:
                print(f"[WebAdmin] profile registration insert failed: HTTP {create_response.status_code} {create_response.text[:300]}")
                return {"success": False, "error": "가입 신청 프로필 생성에 실패했습니다."}
        return {"success": True, "status": "pending"}

    def fetch_profiles(self, select: str = "*") -> List[Dict[str, Any]]:
        response = self.supabase_get("profiles", params={"select": select}, timeout=5)
        if response is not None and response.status_code == 200:
            return response.json()
        return []

    def fetch_categories(self, select: str = "id,name") -> List[Dict[str, Any]]:
        response = self.supabase_get(
            "categories",
            params={"select": select, "order": "created_at.desc"},
            timeout=5,
        )
        if response is not None and response.status_code == 200:
            try:
                return response.json() or []
            except Exception:
                return []
        return []

    def insert_withdrawal_request(self, email: str, amount: float, destination_address: str) -> bool:
        return bool(self.submit_withdrawal_request(email, amount, destination_address))

    def update_user_metadata(self, user_id: str, new_metadata: Dict[str, Any]) -> bool:
        """Updates the user_metadata field for a user via Admin API."""
        if not self.has_supabase() or not user_id:
            return False
        self._disable_warnings()
        try:
            response = requests.put(
                f"{self.supabase_url}/auth/v1/admin/users/{user_id}",
                headers=self.headers(content_type=True),
                json={"user_metadata": new_metadata},
                timeout=self.timeout,
                verify=False,
                proxies={"http": None, "https": None},
            )
            return response.status_code == 200
        except Exception as e:
            print(f"[Supabase] Failed to update user metadata: {e}")
            return False

    def fetch_auth_user_by_email(self, email: str) -> Optional[Dict[str, Any]]:
        if not self.has_supabase() or not email:
            return None
        self._disable_warnings()
        response = requests.get(
            f"{self.supabase_url}/auth/v1/admin/users",
            headers=self.headers(content_type=True),
            timeout=self.timeout,
            verify=False,
            proxies={"http": None, "https": None},
        )
        if response.status_code == 200:
            users = response.json()
            if isinstance(users, dict) and "users" in users:
                users = users["users"]
            for u in users:
                if u.get("email") == email:
                    return u
        return None

    def desktop_login(self, email: str, password: str, lang: str = "") -> Dict[str, Any]:
        """로그인 검증을 auth-web(Vercel) 서버에 위임한다.
        SUPABASE_SERVICE_ROLE_KEY를 데스크톱 앱이 직접 쓰지 않도록,
        비밀번호/pin_code 비교를 서버 쪽 /api/desktop-login에서 수행하고
        결과만 돌려받는다.

        [AIR-0225B Batch A] 같은 요청에서 회원등급(membership)/토큰잔액
        (token_balance)/공용 API 키(global_settings)까지 함께 받아오고,
        lang이 주어지면 preferred_language 저장까지 서버 쪽에서 같이
        처리한다 - 로그인 직후 데스크톱이 따로 service_role로
        fetch_profile_by_email()/fetch_global_api_keys()/
        update_preferred_language()를 호출하지 않아도 되게 하기 위함."""
        try:
            payload = {"email": email, "password": password}
            if lang:
                payload["lang"] = lang
            response = requests.post(
                f"{self.dashboard_url}/api/desktop-login",
                json=payload,
                headers=self.dashboard_headers(content_type=True),
                timeout=self.timeout,
            )
            try:
                data = response.json()
            except Exception:
                return {"success": False, "error": f"Login server returned HTTP {response.status_code}"}
            if not isinstance(data, dict):
                return {"success": False, "error": "로그인 서버 응답 오류"}
            if not data.get("success"):
                data["error"] = _human_error(data.get("error"), f"Login failed (HTTP {response.status_code})")
            return data
        except Exception as e:
            return {"success": False, "error": f"로그인 서버 연결 오류: {e}"}

    def desktop_resync(self, email: str, session_token: str) -> Dict[str, Any]:
        """비밀번호 없이 세션을 재개한다 (앱 재실행, 쿠키 기반 재접속, 주기적 동기화).
        [AIR-0225B Batch A] auth-web이 로그인 시 발급한 session_token(HMAC 서명,
        DESKTOP_SESSION_SECRET으로만 검증 가능)을 함께 보내야 하며, 이메일만으로는
        절대 회원등급/토큰잔액/공용 API키를 내려주지 않는다 - 그렇지 않으면 이메일만
        아는 누구나 그 정보를 조회할 수 있는 구멍이 된다."""
        try:
            response = requests.post(
                f"{self.dashboard_url}/api/desktop-resync",
                json={"email": email, "session_token": session_token},
                headers=self.dashboard_headers(content_type=True),
                timeout=self.timeout,
            )
            data = response.json()
            if not isinstance(data, dict):
                return {"success": False, "error": "동기화 서버 응답 오류"}
            return data
        except Exception as e:
            return {"success": False, "error": f"동기화 서버 연결 오류: {e}"}

    def desktop_referrals(
        self,
        email: str,
        session_token: str,
        action: str,
        params: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """추천인/출금 조회·신청을 auth-web(Vercel) 서버에 위임한다.
        [AIR-0225B Phase 1] app/routers/referral.py가 SUPABASE_SERVICE_ROLE_KEY로
        직접 조회하던 6개 액션(dashboard/tree/timeline/withdrawal_info/withdraw/
        withdrawal_history)을 session_token 검증 기반 브릿지로 이전. 출금 잔액
        검증도 이제 서버에서 수행된다."""
        try:
            payload: Dict[str, Any] = {
                "email": email,
                "session_token": session_token,
                "action": action,
            }
            payload.update(params or {})
            response = requests.post(
                f"{self.dashboard_url}/api/desktop-referrals",
                json=payload,
                headers=self.dashboard_headers(content_type=True),
                timeout=self.timeout,
            )
            data = response.json()
            if not isinstance(data, dict):
                return {"success": False, "error": "추천인 서버 응답 오류"}
            return data
        except Exception as e:
            return {"success": False, "error": f"추천인 서버 연결 오류: {e}"}

    def desktop_support(
        self,
        email: str,
        session_token: str,
        action: str,
        params: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """유저 -> 웹어드민 문의 전송/조회를 auth-web(Vercel) 서버에 위임한다.
        desktop_referrals와 동일한 session_token 검증 기반 브릿지 - 문의는
        AI 초안(있으면)이 서버 측에서 자동 생성되지만, list 응답에는 절대
        포함되지 않는다(어드민이 확정 발송한 답장만 노출)."""
        try:
            payload: Dict[str, Any] = {
                "email": email,
                "session_token": session_token,
                "action": action,
            }
            payload.update(params or {})
            response = requests.post(
                f"{self.dashboard_url}/api/desktop-support",
                json=payload,
                headers=self.dashboard_headers(content_type=True),
                timeout=self.timeout,
            )
            data = response.json()
            if not isinstance(data, dict):
                return {"success": False, "error": "문의 서버 응답 오류"}
            return data
        except Exception as e:
            return {"success": False, "error": f"문의 서버 연결 오류: {e}"}

    def desktop_announcements(self, email: str, session_token: str, lang: str = "ko") -> Dict[str, Any]:
        """웹어드민이 전체 유저에게 발행한 공지사항 게시판 목록을 조회한다.
        쪽지(1:1)가 아니라 게시판(1:N) - 모든 유저가 동일한 글을 본다.
        session_token 검증은 미승인/비로그인 클라이언트의 내부 공지 열람을
        막기 위함이지 개인화를 위한 것이 아니다.
        [AIR-0229] lang을 함께 보내면 auth-web이 저장해둔 자동번역
        (title_en/title_vi/title_th 등)을 title/body 자리에 대신 채워 응답한다."""
        try:
            response = requests.post(
                f"{self.dashboard_url}/api/desktop-announcements",
                json={"email": email, "session_token": session_token, "action": "list", "lang": lang},
                headers=self.dashboard_headers(content_type=True),
                timeout=self.timeout,
            )
            data = response.json()
            if not isinstance(data, dict):
                return {"success": False, "error": "공지사항 서버 응답 오류"}
            return data
        except Exception as e:
            return {"success": False, "error": f"공지사항 서버 연결 오류: {e}"}

    def desktop_project_sync(
        self,
        email: str,
        session_token: str,
        action: str,
        params: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """[AIR-0225B] desktop_project_metadata 테이블 접근을 session_token
        브릿지로 위임한다. 예전에는 services/project_sync_service.py가
        SUPABASE_SERVICE_ROLE_KEY로 직접 조회/upsert했는데, 그 키가 패키징된
        빌드에서 제거된 뒤로 has_supabase()가 항상 False가 되어 프로젝트
        복원(fetch_remote_projects/ensure_local_projects_from_remote)이
        에러 없이 조용히 0건으로 끝나고 있었다 - 새 설치에서 프로젝트
        목록이 비어 보이는 원인."""
        try:
            payload: Dict[str, Any] = {
                "email": email,
                "session_token": session_token,
                "action": action,
            }
            payload.update(params or {})
            response = requests.post(
                f"{self.dashboard_url}/api/desktop-project-sync",
                json=payload,
                headers=self.dashboard_headers(content_type=True),
                timeout=self.timeout,
            )
            data = response.json()
            if not isinstance(data, dict):
                return {"success": False, "error": "프로젝트 동기화 서버 응답 오류"}
            return data
        except Exception as e:
            return {"success": False, "error": f"프로젝트 동기화 서버 연결 오류: {e}"}

    def desktop_update_profile(
        self,
        email: str,
        session_token: str,
        *,
        full_name: str = "",
        nationality: str = "",
        contact: str = "",
        preferred_category_ids: Optional[list] = None,
    ) -> Dict[str, Any]:
        """설정 페이지의 회원정보(이름/국적/연락처/선호 카테고리) 저장을
        auth-web(Vercel) 서버에 위임한다. [AIR-0225B Phase 1] 기존에는
        supabase_patch("profiles", ...)로 SUPABASE_SERVICE_ROLE_KEY를 직접
        썼으나, 그 키가 패키징된 앱에서 제거되어 더 이상 동작하지 않는다."""
        try:
            response = requests.post(
                f"{self.dashboard_url}/api/desktop-profile-update",
                json={
                    "email": email,
                    "session_token": session_token,
                    "full_name": full_name,
                    "nationality": nationality,
                    "contact": contact,
                    "preferred_category_ids": preferred_category_ids or [],
                },
                headers=self.dashboard_headers(content_type=True),
                timeout=self.timeout,
            )
            data = response.json()
            if not isinstance(data, dict):
                return {"success": False, "error": "프로필 저장 서버 응답 오류"}
            return data
        except Exception as e:
            return {"success": False, "error": f"프로필 저장 서버 연결 오류: {e}"}

    def desktop_change_password(self, email: str, current_password: str, new_password: str) -> Dict[str, Any]:
        """비밀번호 변경을 auth-web(Vercel) 서버에 위임한다.
        SUPABASE_SERVICE_ROLE_KEY를 데스크톱 앱이 직접 쓰지 않도록,
        현재 비밀번호 확인/신규 비밀번호 저장을 서버 쪽
        /api/desktop-change-password에서 수행하고 결과만 돌려받는다."""
        try:
            response = requests.post(
                f"{self.dashboard_url}/api/desktop-change-password",
                json={
                    "email": email,
                    "current_password": current_password,
                    "new_password": new_password,
                },
                headers=self.dashboard_headers(content_type=True),
                timeout=self.timeout,
            )
            data = response.json()
            if not isinstance(data, dict):
                return {"success": False, "error": "비밀번호 변경 서버 응답 오류"}
            return data
        except Exception as e:
            return {"success": False, "error": f"비밀번호 변경 서버 연결 오류: {e}"}

    def fetch_profile_by_email(self, email: str, select: str = "*") -> Optional[Dict[str, Any]]:
        if not email:
            return None
        response = self.supabase_get(
            "profiles",
            params={"select": select, "email": f"eq.{email}"},
            timeout=5,
        )
        if response is not None and response.status_code == 200 and response.json():
            return response.json()[0]
        return None

    def update_preferred_language(self, email: str, lang: str) -> bool:
        """Save UI display language preference to profiles.preferred_language.
        NOTE: This is separate from preferred_languages (content/topic language array).
        """
        allowed = {"ko", "en", "vi", "th"}
        if not email or lang not in allowed:
            return False
        try:
            response = self.supabase_patch(
                "profiles",
                {"preferred_language": lang},
                params={"email": f"eq.{email}"},
                timeout=5,
            )
            if response is not None and response.status_code < 400:
                print(f"[WebAdmin] preferred_language updated: {email} → {lang}")
                return True
            if response is not None:
                print(f"[WebAdmin] preferred_language update failed: HTTP {response.status_code}")
        except Exception as e:
            print(f"[WebAdmin] preferred_language update error: {e}")
        return False

    def resolve_user_id(self, *, email: str = "", candidate: str = "") -> str:
        candidate = (candidate or "").strip()
        if UUID_RE.fullmatch(candidate):
            return candidate

        lookup_email = email or (candidate if "@" in candidate else "")
        profile = self.fetch_profile_by_email(lookup_email, select="id")
        return (profile or {}).get("id") or ""

    def fetch_global_setting_values(self, keys: List[str]) -> Dict[str, Any]:
        if not keys:
            return {}
        response = self.supabase_get(
            "global_settings",
            params={"select": "key,value", "key": f"in.({','.join(keys)})"},
            timeout=5,
        )
        if response is None or response.status_code != 200:
            return {}
        return {item.get("key"): item.get("value") for item in response.json() or []}

    def save_global_setting(self, key: str, value: str) -> bool:
        """Supabase global_settings 테이블에 key, value 값을 업서트한다."""
        return self.upsert_by_key("global_settings", "key", key, {"key": key, "value": value})

    def translate_global_settings_rows(self, rows: List[Dict[str, Any]]) -> Dict[str, str]:
        """global_settings의 {key,value} 원시 행 목록을 KEY_MAP으로 변환한다.
        [AIR-0225B Batch A] fetch_global_api_keys()(직접 service_role 조회)와
        desktop_login()의 presynced global_settings(auth-web에서 이미 받아온
        원시 행) 양쪽이 동일한 매핑 로직을 공유하기 위해 분리했다."""
        keys: Dict[str, str] = {}
        for item in rows or []:
            config_key = self.KEY_MAP.get(item.get("key"))
            value = item.get("value")
            if config_key and value:
                keys[config_key] = value
        return keys

    def fetch_global_api_keys(self) -> Dict[str, str]:
        response = self.supabase_get("global_settings", params={"select": "key,value"}, timeout=8)
        if response is None or response.status_code != 200:
            if response is not None:
                print(f"[WebAdmin] global_settings load failed: HTTP {response.status_code} {response.text[:200]}")
            return {}
        return self.translate_global_settings_rows(response.json())

    def fetch_script_style_presets(self) -> List[Dict[str, Any]]:
        """웹어드민(auth-web) '스타일 세팅 > 대본 스타일' 탭이 관리하는 Supabase
        style_presets(preset_type=script) 행을 가져온다. 이걸 로컬 SQLite
        script_style_presets로 동기화해야 실제 대본 생성기가 반영한다 -
        services/script_style_resolver.py 참고."""
        response = self.supabase_get(
            "style_presets",
            params={
                "select": "key_code,display_name_ko,display_name_vi,prompt_template",
                "preset_type": "eq.script",
            },
            timeout=8,
        )
        if response is None or response.status_code != 200:
            if response is not None:
                print(f"[WebAdmin] script style presets load failed: HTTP {response.status_code} {response.text[:200]}")
            return []
        try:
            return response.json() or []
        except Exception:
            return []

    def fetch_style_presets(self, preset_types: Optional[List[str]] = None) -> List[Dict[str, Any]]:
        """Fetch shared image/script style presets for the local Worker console.

        The Supabase table is the source of truth.  The Worker keeps a local
        cache for generation, but editing must update this shared record first
        so the desktop app and Worker cannot quietly drift apart.
        """
        params: Dict[str, Any] = {
            "select": "id,preset_type,key_code,display_name_ko,display_name_vi,prompt_template,gemini_instruction,image_url,created_at",
            "order": "created_at.desc",
        }
        if preset_types:
            params["preset_type"] = "in.(" + ",".join(preset_types) + ")"
        response = self.supabase_get("style_presets", params=params, timeout=10)
        if response is None or response.status_code != 200:
            if response is not None:
                print(f"[WebAdmin] style presets load failed: HTTP {response.status_code} {response.text[:200]}")
            return []
        try:
            return response.json() or []
        except Exception:
            return []

    def upsert_style_preset(self, preset: Dict[str, Any]) -> Dict[str, Any]:
        """Create or update one shared image/script preset by key_code."""
        if not self.has_supabase():
            return {"success": False, "error": "중앙 스타일 저장소 연결 설정이 없습니다."}
        key_code = str(preset.get("key_code") or "").strip().lower()
        if not key_code:
            return {"success": False, "error": "스타일 코드가 비어 있습니다."}
        payload = dict(preset)
        payload["key_code"] = key_code
        self._disable_warnings()
        headers = self.headers(content_type=True)
        headers["Prefer"] = "resolution=merge-duplicates,return=representation"
        try:
            response = requests.post(
                f"{self.supabase_url}/rest/v1/style_presets?on_conflict=key_code",
                headers=headers,
                json=payload,
                timeout=10,
                verify=False,
                proxies={"http": None, "https": None},
            )
            if response.status_code >= 300:
                return {"success": False, "error": f"스타일 저장 실패 (HTTP {response.status_code})"}
            rows = response.json() or []
            return {"success": True, "preset": rows[0] if rows else payload}
        except Exception as e:
            return {"success": False, "error": f"스타일 저장 연결 오류: {e}"}

    def delete_style_preset(self, key_code: str) -> Dict[str, Any]:
        """Delete a shared style preset by its stable key."""
        if not self.has_supabase():
            return {"success": False, "error": "중앙 스타일 저장소 연결 설정이 없습니다."}
        try:
            response = requests.delete(
                f"{self.supabase_url}/rest/v1/style_presets",
                headers=self.headers(),
                params={"key_code": f"eq.{key_code}"},
                timeout=10,
                verify=False,
                proxies={"http": None, "https": None},
            )
            if response.status_code >= 300:
                return {"success": False, "error": f"스타일 삭제 실패 (HTTP {response.status_code})"}
            return {"success": True}
        except Exception as e:
            return {"success": False, "error": f"스타일 삭제 연결 오류: {e}"}

    def fetch_music_plan_templates(self) -> List[Dict[str, Any]]:
        response = self.supabase_get(
            "style_presets",
            params={
                "select": "id,key_code,display_name_ko,display_name_vi,prompt_template,gemini_instruction,image_url,created_at",
                "preset_type": "eq.music_plan",
                "order": "created_at.desc",
            },
            timeout=8,
        )
        if response is None or response.status_code != 200:
            if response is not None:
                print(f"[WebAdmin] music plan templates load failed: HTTP {response.status_code} {response.text[:200]}")
            return []
        try:
            return response.json() or []
        except Exception:
            return []



    def sync_wallet_info(self, email: str, usdt_balance: float, wallet_address: str):
        if not self.has_supabase() or not email:
            return False
            
        # 1. Get user_id by email
        res = self.supabase_get("profiles", params={"email": f"eq.{email}", "select": "id"})
        if not res or res.status_code != 200:
            return False
            
        data = res.json()
        if not data:
            return False
            
        user_id = data[0]["id"]
        
        # 2. Patch profiles
        patch_res = self.supabase_patch(
            "profiles",
            {"usdt_balance": usdt_balance, "wallet_address": wallet_address},
            params={"id": f"eq.{user_id}"}
        )
        return patch_res and patch_res.status_code in (200, 204)

    def submit_withdrawal_request(self, email: str, amount: float, dest_address: str) -> Optional[str]:
        if not self.has_supabase() or not email:
            return None
            
        # 1. Get user_id by email
        res = self.supabase_get("profiles", params={"email": f"eq.{email}", "select": "id"})
        if not res or res.status_code != 200:
            return None
            
        data = res.json()
        if not data:
            return None
            
        user_id = data[0]["id"]
        
        # 2. Insert withdrawal
        post_res = self.supabase_post(
            "withdrawals",
            {
                "user_id": user_id,
                "amount": amount,
                "dest_address": dest_address,
                "status": "pending"
            }
        )
        if not post_res or post_res.status_code not in (201, 204):
            return None
            
        # If possible, get the returned ID, or just return true
        if post_res.text:
            try:
                ret_data = post_res.json()
                if isinstance(ret_data, list) and len(ret_data) > 0:
                    return ret_data[0].get("id", "success")
                return "success"
            except:
                return "success"
        return "success"

    def get_withdrawal_history(self, email: str) -> List[Dict[str, Any]]:
        if not self.has_supabase() or not email:
            return []
            
        # 1. Get user_id by email
        res = self.supabase_get("profiles", params={"email": f"eq.{email}", "select": "id"})
        if not res or res.status_code != 200:
            return []
            
        data = res.json()
        if not data:
            return []
            
        user_id = data[0]["id"]
        
        # 2. Get withdrawals
        hist_res = self.supabase_get(
            "withdrawals",
            params={
                "user_id": f"eq.{user_id}",
                "order": "created_at.desc",
                "select": "id,amount,dest_address,status,created_at"
            }
        )
        if not hist_res or hist_res.status_code != 200:
            return []
            
        return hist_res.json()

    def delete_auth_user(self, user_id: str) -> bool:
        """Supabase auth.users에서 사용자 계정 삭제 (Admin API)"""
        if not self.has_supabase() or not user_id:
            return False
        self._disable_warnings()
        try:
            response = requests.delete(
                f"{self.supabase_url}/auth/v1/admin/users/{user_id}",
                headers=self.headers(),
                timeout=self.timeout,
                verify=False,
                proxies={"http": None, "https": None},
            )
            if response.status_code in (200, 204):
                print(f"[WebAdmin] Successfully deleted auth user {user_id}")
                return True
            else:
                print(f"[WebAdmin] Failed to delete auth user {user_id}: HTTP {response.status_code} {response.text}")
                return False
        except Exception as e:
            print(f"[WebAdmin] Error deleting auth user: {e}")
            return False

    def delete_profile(self, user_id: str) -> bool:
        """Supabase profiles 테이블에서 프로필 삭제"""
        if not self.has_supabase() or not user_id:
            return False
        self._disable_warnings()
        try:
            response = requests.delete(
                f"{self.supabase_url}/rest/v1/profiles",
                headers=self.headers(),
                params={"id": f"eq.{user_id}"},
                timeout=self.timeout,
                verify=False,
                proxies={"http": None, "https": None},
            )
            if response.status_code in (200, 204):
                print(f"[WebAdmin] Successfully deleted profile {user_id}")
                return True
            else:
                print(f"[WebAdmin] Failed to delete profile {user_id}: HTTP {response.status_code} {response.text}")
                return False
        except Exception as e:
            print(f"[WebAdmin] Error deleting profile: {e}")
            return False

    def delete_withdrawals(self, user_id: str) -> bool:
        """Supabase withdrawals 테이블에서 해당 유저의 출금 신청 기록 삭제"""
        if not self.has_supabase() or not user_id:
            return False
        self._disable_warnings()
        try:
            response = requests.delete(
                f"{self.supabase_url}/rest/v1/withdrawals",
                headers=self.headers(),
                params={"user_id": f"eq.{user_id}"},
                timeout=self.timeout,
                verify=False,
                proxies={"http": None, "https": None},
            )
            return response.status_code in (200, 204)
        except Exception as e:
            print(f"[WebAdmin] Error deleting withdrawals: {e}")
            return False

    # ─────────────────────────────────────────────
    # 테넌트 관련 함수
    # ─────────────────────────────────────────────

    def get_all_tenants(self) -> List[Dict[str, Any]]:
        """모든 테넌트 목록 조회"""
        if not self.has_supabase():
            return []
        response = self.supabase_get(
            "tenant_configs",
            params={
                "select": "*",
                "order": "created_at.desc"
            },
            timeout=8
        )
        if response and response.status_code == 200:
            return response.json() or []
        return []

    def get_tenant_by_key(self, tenant_key: str) -> Optional[Dict[str, Any]]:
        """테넌트 키로 테넌트 조회"""
        if not self.has_supabase() or not tenant_key:
            return None
        response = self.supabase_get(
            "tenant_configs",
            params={
                "select": "*",
                "tenant_key": f"eq.{tenant_key}"
            },
            timeout=8
        )
        if response and response.status_code == 200:
            data = response.json()
            if data:
                return data[0]
        return None

    def update_tenant_commission(
        self,
        tenant_key: str,
        commission_percent: float,
        min_commission_usd: float = 0
    ) -> Dict[str, Any]:
        """테넌트 수수료 설정 업데이트 (슈퍼어드민용)"""
        if not self.has_supabase() or not tenant_key:
            return {"success": False, "error": "invalid_params"}

        # Supabase RPC 함수 호출
        response = requests.post(
            f"{self.supabase_url}/rest/v1/rpc/admin_update_tenant_commission",
            headers=self.headers(content_type=True),
            json={
                "p_tenant_key": tenant_key,
                "p_commission_percent": commission_percent,
                "p_min_commission_usd": min_commission_usd
            },
            timeout=10,
            verify=False,
            proxies={"http": None, "https": None},
        )

        if response.status_code == 200:
            try:
                return response.json() or {"success": True}
            except Exception:
                return {"success": True}
        else:
            return {
                "success": False,
                "error": f"HTTP {response.status_code}",
                "details": response.text[:200]
            }

    def calculate_user_commission(self, user_id: str, amount_usd: float) -> Dict[str, Any]:
        """사용자 수수료 계산"""
        if not self.has_supabase() or not user_id:
            return {"error": "invalid_params"}

        response = requests.post(
            f"{self.supabase_url}/rest/v1/rpc/calculate_commission",
            headers=self.headers(content_type=True),
            json={
                "p_user_id": user_id,
                "p_amount_usd": amount_usd
            },
            timeout=10,
            verify=False,
            proxies={"http": None, "https": None},
        )

        if response.status_code == 200:
            try:
                return response.json() or {}
            except Exception:
                return {}
        else:
            return {"error": f"HTTP {response.status_code}"}

    def get_user_watermark(self, user_id: str) -> Dict[str, Any]:
        """사용자의 테넌트 워터마크 설정 조회"""
        if not self.has_supabase() or not user_id:
            return {"enabled": False}

        response = requests.post(
            f"{self.supabase_url}/rest/v1/rpc/get_tenant_watermark",
            headers=self.headers(content_type=True),
            json={"p_user_id": user_id},
            timeout=10,
            verify=False,
            proxies={"http": None, "https": None},
        )

        if response.status_code == 200:
            try:
                return response.json() or {"enabled": False}
            except Exception:
                return {"enabled": False}
        return {"enabled": False}

    def get_tenant_users(self, tenant_key: str) -> List[Dict[str, Any]]:
        """테넌트 소속 사용자 목록"""
        if not self.has_supabase() or not tenant_key:
            return []

        response = self.supabase_get(
            "tenant_users",
            params={
                "select": "*,profiles(email,full_name)",
                "tenant_key": f"eq.{tenant_key}",
                "order": "created_at.desc"
            },
            timeout=8
        )

        if response and response.status_code == 200:
            return response.json() or []
        return []

    def update_user_tenant(
        self,
        user_id: str,
        tenant_key: str,
        commission_percent: Optional[float] = None
    ) -> bool:
        """사용자 테넌트 및 수수료 설정 업데이트"""
        if not self.has_supabase() or not user_id or not tenant_key:
            return False

        # profiles 테이블 업데이트
        update_data = {"tenant_key": tenant_key}
        if commission_percent is not None:
            update_data["commission_percent"] = commission_percent

        patch_res = self.supabase_patch(
            "profiles",
            update_data,
            params={"id": f"eq.{user_id}"}
        )

        return patch_res and patch_res.status_code in (200, 204)


web_admin_client = WebAdminClient()
