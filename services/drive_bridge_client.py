import time

import requests

from services.auth_service import auth_service
from services.web_admin_client import web_admin_client

# [AIR-drive-bridge] Exchanges the server-held Drive/YouTube refresh_token for
# a short-lived access_token via auth-web's /api/desktop-drive-token, instead
# of loading a local token.pickle. Two callers authenticate differently:
#   - user-app (desktop, logged-in employee): email + session_token
#   - render worker (single trusted machine): its own SUPABASE_SERVICE_ROLE_KEY
# The access_token is cached in-process and refreshed shortly before expiry.

_REFRESH_MARGIN_SECONDS = 300
_cache = {"token": None, "expires_at": 0.0, "root_folder_id": None}


class DriveBridgeError(Exception):
    pass


def _request_token():
    email = auth_service.get_user_email()
    session_token = auth_service.get_session_token()
    if email and session_token:
        body = {"email": email, "session_token": session_token}
    else:
        worker_key = web_admin_client.supabase_key
        if not worker_key:
            raise DriveBridgeError(
                "No logged-in desktop session and no SUPABASE_SERVICE_ROLE_KEY "
                "available to authenticate to the Drive bridge."
            )
        body = {"worker_key": worker_key}

    try:
        r = requests.post(
            f"{web_admin_client.dashboard_url}/api/desktop-drive-token",
            json=body,
            timeout=15,
        )
    except Exception as e:
        raise DriveBridgeError(f"desktop-drive-token bridge unreachable: {e}")

    try:
        resp = r.json()
    except Exception:
        raise DriveBridgeError(
            f"desktop-drive-token bridge returned a non-JSON response (HTTP {r.status_code})"
        )

    if r.status_code != 200 or resp.get("status") != "ok" or not resp.get("access_token"):
        raise DriveBridgeError(f"desktop-drive-token bridge error: {resp.get('detail') or r.status_code}")

    return resp


def get_access_token(force_refresh=False):
    now = time.time()
    if not force_refresh and _cache["token"] and now < _cache["expires_at"]:
        return _cache["token"]

    resp = _request_token()
    expires_in = resp.get("expires_in") or 3600
    _cache["token"] = resp["access_token"]
    _cache["expires_at"] = now + max(expires_in - _REFRESH_MARGIN_SECONDS, 30)
    _cache["root_folder_id"] = resp.get("root_folder_id")
    return _cache["token"]


def get_root_folder_id():
    if _cache["token"] is None:
        get_access_token()
    return _cache["root_folder_id"]
