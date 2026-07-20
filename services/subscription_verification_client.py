import requests

from services.auth_service import auth_service
from services.web_admin_client import web_admin_client

# [AIR-0228 Stage 3] Thin proxy wrapper around auth-web's subscription
# verification endpoints. No scoring/approval logic lives here or anywhere
# else in the desktop app - the analysis/approval decision runs entirely on
# auth-web (docs/CHATGPT_PLUS_VERIFICATION_SECURITY.md §1). This file only
# forwards the uploaded file and reads back status.


class SubscriptionVerificationError(Exception):
    pass


def _auth_params():
    email = auth_service.get_user_email()
    session_token = auth_service.get_session_token()
    if not email or not session_token:
        raise SubscriptionVerificationError("로그인이 필요합니다.")
    return email, session_token


def submit_verification(provider: str, file_path: str, filename: str, mimetype: str) -> dict:
    email, session_token = _auth_params()
    try:
        with open(file_path, "rb") as f:
            resp = requests.post(
                f"{web_admin_client.dashboard_url}/api/subscription-verifications",
                data={"email": email, "session_token": session_token, "provider": provider},
                files={"file": (filename, f, mimetype)},
                timeout=60,
            )
    except Exception as e:
        raise SubscriptionVerificationError(f"업로드 서버에 연결할 수 없습니다: {e}")

    try:
        body = resp.json()
    except Exception:
        raise SubscriptionVerificationError(f"서버 응답을 해석할 수 없습니다 (HTTP {resp.status_code})")

    if resp.status_code == 401:
        raise SubscriptionVerificationError("인증이 만료되었습니다. 다시 로그인해주세요.")
    if body.get("status") != "ok":
        raise SubscriptionVerificationError(body.get("detail") or "제출에 실패했습니다.")
    return body


def get_status(provider: str) -> dict:
    email, session_token = _auth_params()
    try:
        resp = requests.get(
            f"{web_admin_client.dashboard_url}/api/subscription-verifications",
            params={"email": email, "session_token": session_token, "provider": provider},
            timeout=15,
        )
    except Exception as e:
        raise SubscriptionVerificationError(f"상태 조회 서버에 연결할 수 없습니다: {e}")

    try:
        body = resp.json()
    except Exception:
        raise SubscriptionVerificationError(f"서버 응답을 해석할 수 없습니다 (HTTP {resp.status_code})")

    if resp.status_code == 401:
        raise SubscriptionVerificationError("인증이 만료되었습니다. 다시 로그인해주세요.")
    if body.get("status") != "ok":
        raise SubscriptionVerificationError(body.get("detail") or "조회에 실패했습니다.")
    return body


def get_active_badges() -> list:
    email = auth_service.get_user_email()
    session_token = auth_service.get_session_token()
    if not email or not session_token:
        return []
    try:
        resp = requests.get(
            f"{web_admin_client.dashboard_url}/api/badges/me",
            params={"email": email, "session_token": session_token},
            timeout=10,
        )
        body = resp.json()
        if body.get("status") == "ok":
            return body.get("badges") or []
    except Exception:
        pass
    return []
