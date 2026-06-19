import os
import re
from typing import Any, Dict, List, Optional

import requests
from dotenv import load_dotenv


load_dotenv()


UUID_RE = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)


class WebAdminClient:
    """Small wrapper for Vercel web-admin and Supabase REST integration."""

    KEY_MAP = {
        "sys_api_gemini": "GEMINI_API_KEY",
        "sys_api_youtube": "YOUTUBE_API_KEY",
        "sys_api_elevenlabs": "ELEVENLABS_API_KEY",
        "sys_api_suno": "SUNO_API_KEY",
        "sys_api_suno_base_url": "SUNO_API_BASE_URL",
        "sys_api_music_provider": "MUSIC_PROVIDER",
        "sys_api_topview": "TOPVIEW_API_KEY",
        "sys_api_topview_uid": "TOPVIEW_UID",
        "sys_api_remote_render_drive_folder_id": "REMOTE_RENDER_DRIVE_FOLDER_ID",
        "sys_api_remote_render_google_token_path": "REMOTE_RENDER_GOOGLE_TOKEN_PATH",
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

    def supabase_post(self, table: str, payload: Dict[str, Any], *, timeout: Optional[int] = None):
        if not self.has_supabase():
            return None
        self._disable_warnings()
        return requests.post(
            f"{self.supabase_url}/rest/v1/{table}",
            headers=self.headers(content_type=True),
            json=payload,
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

    def fetch_profiles(self, select: str = "*") -> List[Dict[str, Any]]:
        response = self.supabase_get("profiles", params={"select": select}, timeout=5)
        if response is not None and response.status_code == 200:
            return response.json()
        return []

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

    def resolve_user_id(self, *, email: str = "", candidate: str = "") -> str:
        candidate = (candidate or "").strip()
        if UUID_RE.fullmatch(candidate):
            return candidate

        lookup_email = email or (candidate if "@" in candidate else "")
        profile = self.fetch_profile_by_email(lookup_email, select="id")
        return (profile or {}).get("id") or ""

    def fetch_global_api_keys(self) -> Dict[str, str]:
        response = self.supabase_get("global_settings", params={"select": "key,value"}, timeout=8)
        if response is None or response.status_code != 200:
            if response is not None:
                print(f"[WebAdmin] global_settings load failed: HTTP {response.status_code} {response.text[:200]}")
            return {}

        keys = {}
        for item in response.json():
            config_key = self.KEY_MAP.get(item.get("key"))
            value = item.get("value")
            if config_key and value:
                keys[config_key] = value
        return keys

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


web_admin_client = WebAdminClient()
