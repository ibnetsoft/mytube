import json
import os
import re
import time

import requests
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel

import database as db
from services.app_state import get_templates
from services.auth_service import auth_service
from services.email_service import send_temp_password, send_verify_code, generate_temp_password, generate_verify_code
from services.topic_queue_sync_service import sync_topic_progress
from services.web_admin_client import web_admin_client


# 인증 코드 임시 저장소: {email: {code, expires_at}}
_verify_store: dict = {}

router = APIRouter(tags=["Auth"])


class LoginRequest(BaseModel):
    email: str
    password: str
    lang: str | None = None
    browser_lang: str | None = None  # navigator.language detected on client


_LANG_ALLOWED = {"ko", "en", "vi", "th"}


def _detect_lang_from_header(accept_language: str) -> str:
    """Parse Accept-Language header and map to supported lang code.
    Returns 'en' if no match found.
    Mapping: ko* → ko, vi* → vi, th* → th, else → en
    """
    for part in accept_language.split(","):
        tag = part.split(";")[0].strip().lower()
        if tag.startswith("ko"):
            return "ko"
        if tag.startswith("vi"):
            return "vi"
        if tag.startswith("th"):
            return "th"
        if tag.startswith("en"):
            return "en"
    return "en"


def _detect_lang_from_nav(nav_lang: str) -> str:
    """Map navigator.language value (e.g. 'th-TH') to supported lang code."""
    tag = (nav_lang or "").strip().lower()
    if tag.startswith("ko"):
        return "ko"
    if tag.startswith("vi"):
        return "vi"
    if tag.startswith("th"):
        return "th"
    return "en"


class RegisterRequest(BaseModel):
    full_name: str
    contact: str
    email: str
    nationality: str
    password: str = ""
    preferred_category_ids: list[int | str] = []
    preferred_video_length: str = ""
    terms_accepted: bool = False
    privacy_accepted: bool = False
    referral_code: str | None = None


def _supabase_headers():
    supabase_url = os.getenv("NEXT_PUBLIC_SUPABASE_URL")
    supabase_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
    if not supabase_url or not supabase_key:
        return None, None

    return supabase_url.rstrip("/"), {
        "apikey": supabase_key,
        "Authorization": f"Bearer {supabase_key}",
    }


def _disable_insecure_warnings():
    import urllib3

    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


def _apply_login_language(lang: str) -> str:
    """Persist and apply the language selected on the login page."""
    selected = lang if lang in _LANG_ALLOWED else "en"
    try:
        db.save_global_setting("language", selected)
    except Exception as e:
        print(f"[Auth] Failed to save login language to DB: {e}")
    try:
        with open("language.pref", "w", encoding="utf-8") as f:
            f.write(selected)
    except Exception as e:
        print(f"[Auth] Failed to write login language file: {e}")
    # [AIR-0133] Removed app_state.switch_language() — language is now per-request via cookie
    return selected


def _apply_category_upload_channel(project_id: int, category_row: dict):
    """카테고리에 고정 업로드 채널이 있으면 프로젝트 설정에 반영."""
    if not project_id or not category_row:
        return

    upload_handle = (category_row.get("upload_channel_handle") or "").strip()
    upload_name = (category_row.get("upload_channel_name") or "").strip()
    upload_channel_id = category_row.get("upload_channel_id")

    if upload_handle:
        db.update_project_setting(project_id, "preferred_youtube_channel_handle", upload_handle)
    if upload_name:
        db.update_project_setting(project_id, "preferred_youtube_channel_name", upload_name)

    resolved_channel = None
    if upload_handle:
        try:
            resolved_channel = db.get_channel_by_handle(upload_handle)
        except Exception as e:
            print(f"[Queue API Warning] Failed to resolve local channel by handle '{upload_handle}': {e}")

    if resolved_channel and resolved_channel.get("id"):
        db.update_project_setting(project_id, "youtube_channel_id", resolved_channel["id"])
    elif upload_channel_id:
        db.update_project_setting(project_id, "youtube_channel_id", upload_channel_id)


def _to_int(value, default: int) -> int:
    try:
        return int(value)
    except Exception:
        return default


def _to_float(value, default: float) -> float:
    try:
        return float(value)
    except Exception:
        return default


def _normalize_content_language(value, default: str = "ko") -> str:
    lang = (str(value or "").strip().lower() or default)
    return lang if lang in {"ko", "en", "ja"} else default


def _calculate_longform_payout(minutes: int, policy: dict) -> float:
    min_minutes = max(15, _to_int(policy.get("sys_api_longform_min_duration_minutes"), 15))
    base_pay = max(0.0, _to_float(policy.get("sys_api_longform_base_payout"), 4.0))
    extra_pay = max(0.0, _to_float(policy.get("sys_api_longform_extra_minute_payout"), 0.0))
    return round(base_pay + max(0, minutes - min_minutes) * extra_pay, 1)


def _fetch_longform_policy(supabase_url: str, headers: dict) -> dict:
    defaults = {
        "sys_api_longform_min_duration_minutes": "15",
        "sys_api_longform_base_payout": "4",
        "sys_api_longform_extra_minute_payout": "0",
        "sys_api_longform_duration_lock_enabled": "true",
    }
    try:
        keys = ",".join(defaults.keys())
        url = f"{supabase_url}/rest/v1/global_settings?select=key,value&key=in.({keys})"
        r = requests.get(url, headers=headers, timeout=5, verify=False, proxies={"http": None, "https": None})
        if r.status_code == 200:
            for row in r.json() or []:
                if row.get("key"):
                    defaults[row["key"]] = row.get("value")
    except Exception as e:
        print(f"[Queue API Warning] Failed to fetch longform policy: {e}")
    return defaults


@router.get("/login", response_class=HTMLResponse)
async def get_login_page(request: Request):
    templates = get_templates()
    return templates.TemplateResponse(
        request=request,
        name="pages/login.html",
        context={
            "title": "직원 로그인",
            "membership": "std",
            "token_balance": 0,
        },
    )


@router.get("/api/auth/legal")
async def get_legal_settings():
    keys = ["terms_ko", "terms_en", "terms_vi", "privacy_ko", "privacy_en", "privacy_vi"]
    result = {k: "" for k in keys}
    try:
        if web_admin_client.has_supabase():
            keys_str = ",".join(keys)
            res = web_admin_client.supabase_get("global_settings", params={"select": "key,value", "key": f"in.({keys_str})"})
            if res and res.status_code == 200:
                for row in res.json() or []:
                    k = row.get("key")
                    if k in result:
                        result[k] = row.get("value") or ""
    except Exception as e:
        print(f"[Auth API Warning] Failed to fetch legal settings: {e}")
    return result


@router.get("/api/auth/emails")
async def get_auth_emails():
    try:
        profiles = web_admin_client.fetch_profiles(select="email,is_approved")
        emails = [
            item["email"]
            for item in profiles
            if item.get("email") and str(item.get("is_approved")).lower() in ("true", "1", "yes")
        ]
        return {"emails": emails}
    except Exception as e:
        print(f"[API] Failed to fetch emails: {e}")
        return {"emails": []}


_DEFAULT_CATEGORIES = [
    {"id": "default_1", "name": "경제", "video_type": "longform"},
    {"id": "default_2", "name": "탈북사연", "video_type": "longform"},
    {"id": "default_3", "name": "한국사연", "video_type": "longform"},
    {"id": "default_4", "name": "해외감동", "video_type": "longform"},
    {"id": "default_5", "name": "무협", "video_type": "longform"},
    {"id": "default_6", "name": "노후금융", "video_type": "longform"},
    {"id": "default_7", "name": "황혼19금", "video_type": "longform"},
    {"id": "default_8", "name": "옛날이야기", "video_type": "longform"},
]

_DURATION_OPTIONS = [
    {"value": "15m", "label": "15 min"},
    {"value": "30m", "label": "30 min"},
    {"value": "60m_plus", "label": "60+ min"},
]


@router.get("/api/auth/signup-options")
async def get_signup_options():
    normalized_categories = []
    try:
        categories = web_admin_client.fetch_categories(select="id,name")
        for item in categories:
            category_id = item.get("id")
            category_name = str(item.get("name") or "").strip()
            video_type = str(item.get("video_type") or "longform").strip() or "longform"
            if category_id is None or not category_name:
                continue
            normalized_categories.append({
                "id": category_id,
                "name": category_name,
                "video_type": video_type,
            })
    except Exception as e:
        print(f"[API] Failed to fetch signup options from Supabase: {e}")

    if not normalized_categories:
        normalized_categories = _DEFAULT_CATEGORIES

    return {"categories": normalized_categories, "duration_options": _DURATION_OPTIONS}


@router.post("/api/auth/register")
async def post_auth_register(req: RegisterRequest):
    try:
        if not web_admin_client.has_supabase():
            return {"success": False, "error": "서버 DB 연동 설정이 누락되었습니다."}

        full_name = req.full_name.strip()
        contact = req.contact.strip()
        email = req.email.strip().lower()
        nationality = req.nationality.strip()
        password = req.password.strip()
        preferred_video_length = str(req.preferred_video_length or "").strip()
        requested_category_ids = [str(item).strip() for item in (req.preferred_category_ids or []) if str(item).strip()]
        if not all([full_name, contact, email, nationality]):
            return {"success": False, "error": "이름, 연락처, 이메일, 국적은 모두 입력해야 합니다."}
        if "@" not in email or "." not in email:
            return {"success": False, "error": "이메일 형식이 올바르지 않습니다."}
        if not password:
            return {"success": False, "error": "비밀번호를 입력해주세요."}
        password_pattern = re.compile(r'^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)(?=.*[!@#$%^&*()_+\-=\[\]{};\':"\\|,.<>\/?]).{8,}$')
        if not password_pattern.match(password):
            return {"success": False, "error": "비밀번호는 대문자, 소문자, 숫자, 특수문자를 포함한 8자리 이상이어야 합니다."}
        if not req.terms_accepted or not req.privacy_accepted:
            return {"success": False, "error": "약관과 개인정보처리방침에 모두 동의해야 합니다."}
        if not requested_category_ids:
            return {"success": False, "error": "최소 1개 이상의 선호 카테고리를 선택해야 합니다."}
        if preferred_video_length not in {"15m", "30m", "60m_plus"}:
            return {"success": False, "error": "선호 영상 길이를 선택해야 합니다."}

        categories = web_admin_client.fetch_categories(select="id,name")
        category_map = {str(item.get("id")): item for item in categories if item.get("id") is not None}
        preferred_category_ids: list[int | str] = []
        preferred_category_names: list[str] = []
        for category_id in requested_category_ids:
            row = category_map.get(category_id)
            if not row:
                continue
            preferred_category_ids.append(row.get("id"))
            category_name = str(row.get("name") or "").strip()
            if category_name:
                preferred_category_names.append(category_name)
        if not preferred_category_ids:
            return {"success": False, "error": "선택한 카테고리 정보를 찾을 수 없습니다. 다시 시도해주세요."}

        from datetime import datetime, timezone

        now = datetime.now(timezone.utc).isoformat()
        
        existing = web_admin_client.fetch_profile_by_email(email)
        if existing and str(existing.get("is_approved")).lower() in ("true", "1", "yes"):
            return {"success": False, "error": "이미 승인된 이메일입니다. 로그인 화면에서 접속해주세요."}

        referral_code_input = req.referral_code.strip() if req.referral_code else ""
        referred_by_code = ""
        referred_by_id = ""

        if referral_code_input:
            if not web_admin_client.validate_referral_code(referral_code_input):
                return {"success": False, "error": "유효하지 않은 추천코드입니다."}
            referred_by_code = referral_code_input
        else:
            default_sponsor_uuid = web_admin_client.fetch_global_setting("referral_default_sponsor_uuid")
            if default_sponsor_uuid:
                referred_by_id = default_sponsor_uuid

        return web_admin_client.submit_worker_registration({
            "full_name": full_name,
            "contact": contact,
            "email": email,
            "nationality": nationality,
            "terms_accepted_at": now,
            "privacy_accepted_at": now,
            "password": password,
            "preferred_category_ids": preferred_category_ids,
            "preferred_category_names": preferred_category_names,
            "preferred_video_length": preferred_video_length,
            "referred_by_code": referred_by_code,
            "referred_by_id": referred_by_id,
        })
    except Exception as e:
        return {"success": False, "error": f"가입 신청 오류: {str(e)}"}


@router.get("/api/referral/validate")
async def validate_referral_api(code: str):
    """프론트엔드에서 추천코드 유효성을 검증하기 위한 API."""
    if not code or not code.strip():
        return {"success": False, "error": "코드를 입력해주세요."}
    
    is_valid = web_admin_client.validate_referral_code(code)
    if is_valid:
        return {"success": True, "valid": True}
    else:
        return {"success": True, "valid": False}


@router.post("/api/auth/login")
async def post_auth_login(req: LoginRequest, request: Request):
    try:
        # 로그인 검증(비밀번호/pin_code 비교, 승인 상태 확인)은 auth-web 서버에서
        # 수행한다. SUPABASE_SERVICE_ROLE_KEY는 서버에만 있고 데스크톱 앱에는
        # 존재하지 않아도 로그인이 동작해야 하므로, Supabase를 직접 두드리지 않는다.
        #
        # [AIR-0225B Batch A] req.lang이 이미 확정되어 있으면(로그인 화면에서
        # 명시적으로 언어를 고른 경우 - 실사용에서 가장 흔한 경로) 같은 요청
        # 안에서 저장까지 끝낸다. membership/token_balance/global_settings도
        # 이 한 번의 호출로 함께 받아온다.
        precomputed_lang = req.lang if (req.lang and req.lang in _LANG_ALLOWED) else ""
        result = web_admin_client.desktop_login(req.email, req.password, lang=precomputed_lang)
        if not result.get("success"):
            return {"success": False, "error": result.get("error") or "로그인 오류"}

        # [AIR-0132] Language priority:
        # 1. req.lang (user explicitly selected on login page)
        # 2. profile.preferred_language (saved from previous session)
        # 3. req.browser_lang (navigator.language from client)
        # 4. Accept-Language header
        # 5. fallback → en
        db_preferred = result.get("preferred_language") or ""
        nav_lang = (req.browser_lang or "").strip()
        accept_lang = request.headers.get("accept-language", "")

        if precomputed_lang:
            # 이미 위 desktop_login() 호출에서 서버가 저장까지 끝냈다.
            selected_lang = precomputed_lang
        elif db_preferred in _LANG_ALLOWED:
            selected_lang = db_preferred
        elif nav_lang:
            selected_lang = _detect_lang_from_nav(nav_lang)
        elif accept_lang:
            selected_lang = _detect_lang_from_header(accept_lang)
        else:
            selected_lang = "en"

        _apply_login_language(selected_lang)
        auth_service.login_user(req.email, presynced=result)

        if not precomputed_lang:
            # [AIR-0225B Batch A] req.lang이 없었던 드문 경로(브라우저/Accept-Language
            # 기반 추정)만 별도로 저장한다 - service_role 경유, best-effort.
            # 흔한 경로(로그인 화면에서 언어를 직접 고른 경우)는 위에서 이미
            # 한 번의 요청으로 저장이 끝나 이 호출이 발생하지 않는다.
            try:
                web_admin_client.update_preferred_language(req.email, selected_lang)
            except Exception as e:
                print(f"[Auth] preferred_language save warning: {e}")

        response = JSONResponse({"success": True, "lang": selected_lang})
        response.set_cookie(
            key="user_email",
            value=req.email,
            max_age=30 * 24 * 60 * 60,
            httponly=False,
        )
        response.set_cookie(
            key="language",
            value=selected_lang,
            max_age=30 * 24 * 60 * 60,
            httponly=False,
        )
        # [AIR-0225B Batch A] Session token minted by /api/desktop-login, used
        # to resume the session (app relaunch, periodic /api/auth/sync) without
        # a password AND without the local backend needing service_role.
        # HttpOnly - only this local server ever needs to read it back, no
        # desktop UI JS touches it.
        session_token = result.get("session_token")
        if session_token:
            response.set_cookie(
                key="desktop_session_token",
                value=session_token,
                max_age=30 * 24 * 60 * 60,
                httponly=True,
            )
        return response
    except Exception as e:
        return {"success": False, "error": f"로그인 오류: {str(e)}"}


# ===== 비밀번호 찾기 =====
class ForgotPasswordRequest(BaseModel):
    email: str

@router.post("/api/auth/forgot-password")
async def post_forgot_password(req: ForgotPasswordRequest):
    try:
        email = req.email.strip().lower()
        if not email:
            return {"success": False, "error": "이메일을 입력해주세요."}

        profile = web_admin_client.fetch_profile_by_email(email)
        if not profile:
            # 보안상 동일 응답 (이메일 열거 방지)
            return {"success": True, "message": "입력한 이메일로 임시 비밀번호를 발송했습니다."}

        # 임시 비밀번호 생성
        temp_pw = generate_temp_password()

        # DB 업데이트
        patch_response = web_admin_client.supabase_patch(
            "profiles",
            {"pin_code": temp_pw},
            params={"email": f"eq.{email}"},
            timeout=5,
        )
        if patch_response is None or patch_response.status_code >= 400:
            print(f"[ForgotPassword] profile patch failed: {patch_response.text[:300] if patch_response is not None else 'no response'}")
            return {"success": False, "error": "임시 비밀번호 저장에 실패했습니다."}

        # 이메일 발송
        ok = send_temp_password(email, temp_pw)
        if not ok:
            return {"success": False, "error": "이메일 발송에 실패했습니다. SMTP 설정을 확인해주세요."}

        return {"success": True, "message": "임시 비밀번호를 이메일로 발송했습니다."}
    except Exception as e:
        print(f"[ForgotPassword] Error: {e}")
        return {"success": False, "error": f"오류: {str(e)}"}


# ===== 비밀번호 변경 (로그인 중인 유저, 세팅 > 기본설정) =====
class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str
    new_password_confirm: str

@router.post("/api/auth/change-password")
async def post_change_password(req: ChangePasswordRequest):
    try:
        email = auth_service.get_user_email()
        if not email:
            return {"success": False, "error": "로그인이 필요합니다."}

        current_password = req.current_password.strip()
        new_password = req.new_password.strip()
        new_password_confirm = req.new_password_confirm.strip()

        if not current_password or not new_password:
            return {"success": False, "error": "현재 비밀번호와 새 비밀번호를 모두 입력해주세요."}
        if new_password != new_password_confirm:
            return {"success": False, "error": "새 비밀번호가 일치하지 않습니다."}

        password_pattern = re.compile(r'^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)(?=.*[!@#$%^&*()_+\-=\[\]{};\':"\\|,.<>\/?]).{8,}$')
        if not password_pattern.match(new_password):
            return {"success": False, "error": "새 비밀번호는 8자 이상이며 대문자, 소문자, 숫자, 특수문자를 모두 포함해야 합니다."}

        result = web_admin_client.desktop_change_password(email, current_password, new_password)
        if not result.get("success"):
            return {"success": False, "error": result.get("error") or "비밀번호 변경에 실패했습니다."}

        return {"success": True, "message": result.get("message") or "비밀번호가 변경되었습니다."}
    except Exception as e:
        print(f"[ChangePassword] Error: {e}")
        return {"success": False, "error": f"오류: {str(e)}"}


# ===== 내 프로필 (세팅 > 기본설정) =====
@router.get("/api/auth/profile")
async def get_auth_profile():
    try:
        email = auth_service.get_user_email()
        if not email:
            return {"success": False, "error": "로그인이 필요합니다."}

        session_token = auth_service.get_session_token()
        if not session_token:
            return {"success": False, "error": "세션이 만료되었습니다. 다시 로그인해주세요."}

        # [AIR-0225B Phase 1] fetch_profile_by_email()로 SUPABASE_SERVICE_ROLE_KEY를
        # 직접 쓰던 경로 - 그 키가 패키징된 앱에서 제거되어 더 이상 동작하지 않는다
        # (worknote/AIR-0225B-stage0-service-role-removal-investigation.md).
        # /api/auth/sync와 같은 desktop_resync 브릿지로 대체.
        result = web_admin_client.desktop_resync(email, session_token)
        if not result.get("success"):
            return {"success": False, "error": result.get("error") or "프로필을 찾을 수 없습니다."}

        return {
            "success": True,
            "full_name": result.get("full_name") or "",
            "nationality": result.get("nationality") or "",
            "contact": result.get("contact") or "",
            "email": email,
            "preferred_category_ids": result.get("preferred_category_ids") or [],
            "preferred_video_length": result.get("preferred_video_length") or "",
            "categories": result.get("categories") or [],
        }
    except Exception as e:
        print(f"[GetProfile] Error: {e}")
        return {"success": False, "error": f"오류: {str(e)}"}


class UpdateProfileRequest(BaseModel):
    full_name: str = ""
    nationality: str = ""
    contact: str = ""
    preferred_category_ids: list[int | str] = []

@router.post("/api/auth/profile")
async def post_auth_profile(req: UpdateProfileRequest):
    try:
        email = auth_service.get_user_email()
        if not email:
            return {"success": False, "error": "로그인이 필요합니다."}

        session_token = auth_service.get_session_token()
        if not session_token:
            return {"success": False, "error": "세션이 만료되었습니다. 다시 로그인해주세요."}

        result = web_admin_client.desktop_update_profile(
            email,
            session_token,
            full_name=req.full_name.strip(),
            nationality=req.nationality.strip(),
            contact=req.contact.strip(),
            preferred_category_ids=[str(item).strip() for item in (req.preferred_category_ids or []) if str(item).strip()],
        )
        if not result.get("success"):
            print(f"[UpdateProfile] failed: {result.get('error')}")
            return {"success": False, "error": result.get("error") or "프로필 저장에 실패했습니다."}

        return {"success": True, "message": "저장되었습니다."}
    except Exception as e:
        print(f"[UpdateProfile] Error: {e}")
        return {"success": False, "error": f"오류: {str(e)}"}


# ===== 이메일 인증 코드 발송 =====
class SendVerifyCodeRequest(BaseModel):
    email: str

@router.post("/api/auth/send-verify-code")
async def post_send_verify_code(req: SendVerifyCodeRequest):
    try:
        email = req.email.strip().lower()
        if not email or "@" not in email:
            return {"success": False, "error": "이메일 형식이 올바르지 않습니다."}

        # 이미 등록된 이메일 안내
        existing = web_admin_client.fetch_profile_by_email(email)
        if existing and str(existing.get("is_approved")).lower() in ("true", "1", "yes"):
            return {"success": False, "error": "이미 승인된 이메일입니다. 로그인 화면에서 접속해주세요."}

        code = generate_verify_code()
        expires_at = time.time() + 600  # 10분
        _verify_store[email] = {"code": code, "expires_at": expires_at}

        ok = send_verify_code(email, code)
        if not ok:
            return {"success": False, "error": "이메일 발송에 실패했습니다."}

        return {"success": True, "message": "인증 코드를 이메일로 발송했습니다. 10분 내 입력해주세요."}
    except Exception as e:
        print(f"[SendVerifyCode] Error: {e}")
        return {"success": False, "error": f"오류: {str(e)}"}


# ===== 이메일 인증 코드 확인 =====
class VerifyCodeRequest(BaseModel):
    email: str
    code: str

@router.post("/api/auth/verify-code")
async def post_verify_code(req: VerifyCodeRequest):
    email = req.email.strip().lower()
    code = req.code.strip()
    entry = _verify_store.get(email)
    if not entry:
        return {"success": False, "error": "인증 코드를 먼저 발송해주세요."}
    if time.time() > entry["expires_at"]:
        del _verify_store[email]
        return {"success": False, "error": "인증 코드가 만료되었습니다. 다시 발송해주세요."}
    if entry["code"] != code:
        return {"success": False, "error": "인증 코드가 일치하지 않습니다."}
    del _verify_store[email]
    return {"success": True, "message": "이메일 인증이 완료되었습니다."}


@router.post("/api/auth/logout")
async def post_auth_logout():
    auth_service.logout_user()
    response = JSONResponse({"success": True})
    response.delete_cookie("user_email")
    response.delete_cookie("desktop_session_token")
    return response


@router.post("/api/auth/sync")
async def sync_auth(request: Request):
    try:
        from services.updater_service import updater_service
        update_info = updater_service.check_for_update()
        has_update = update_info.get("has_update", False)

        email = auth_service.get_user_email()
        if email:
            # [AIR-0225B Batch A] session_token으로 auth-web /api/desktop-resync를
            # 거쳐 재동기화한다 - 이전에는 여기서 fetch_profile_by_email()로
            # service_role을 직접 썼다. 토큰이 없거나 만료된 경우만 기존 직접
            # 조회로 폴백한다(has_supabase() 가드로 안전하게 실패).
            # 쿠키가 없으면(예: 프론트가 아닌 내부 호출) auth_service에 로그인 시
            # 저장해 둔 토큰으로 폴백한다 - service_role 직접 조회 폴백보다 우선.
            session_token = request.cookies.get("desktop_session_token") or auth_service.get_session_token()
            profile = None
            if session_token:
                resync_result = web_admin_client.desktop_resync(email, session_token)
                if resync_result.get("success"):
                    profile = {
                        "membership": resync_result.get("membership"),
                        "token_balance": resync_result.get("token_balance"),
                    }
                    # [AIR-0225B 자동 복구] 공용 AI 키(global_settings)는 원래
                    # login_user()의 최초 1회 resync에서만 로드된다. 그 한 번이
                    # 실패하면(auth-web 콜드스타트/일시적 네트워크 오류 등) 앱을
                    # 재시작할 때까지 Gemini/Claude 등 모든 AI 기능이 "키 없음"으로
                    # 조용히 죽는다 - 실제 발생 사례 확인됨. sync는 프론트가 모든
                    # 페이지 로드마다 호출하므로, 여기서 같은 응답에 실려 오는
                    # global_settings를 매번 적용해 자연 복구되게 한다.
                    try:
                        rows = resync_result.get("global_settings") or []
                        if rows:
                            sys_keys = web_admin_client.translate_global_settings_rows(rows)
                            if sys_keys:
                                from config import config
                                was_missing = not config.GEMINI_API_KEY
                                loaded = config.load_remote_keys(sys_keys)
                                if loaded and was_missing:
                                    print(f"[Sync] Recovered missing global API keys via resync: {loaded}")
                    except Exception as key_err:
                        print(f"[Sync] Failed to apply global API keys from resync: {key_err}")
            if profile is None:
                profile = web_admin_client.fetch_profile_by_email(email)
            if profile:
                auth_service._membership = profile.get("membership", "std")
                auth_service._token_balance = profile.get("token_balance", 0)

                templates = get_templates()
                if templates:
                    templates.env.globals["membership"] = auth_service._membership
                    templates.env.globals["token_balance"] = auth_service._token_balance
                    templates.env.globals["is_independent"] = auth_service.is_independent()

                return {
                    "success": True,
                    "membership": auth_service.get_membership(),
                    "token_balance": auth_service.get_token_balance(),
                    "has_update": has_update,
                }

            return {"success": False, "error": "Supabase 동기화 실패"}

        success = auth_service.verify_license()

        if success:
            return {
                "success": True,
                "membership": auth_service.get_membership(),
                "token_balance": auth_service.get_token_balance(),
                "has_update": has_update,
            }
        return {"success": False, "error": "Verification failed"}
    except Exception as e:
        return {"success": False, "error": str(e)}


@router.post("/api/topics/get-daily")
async def get_daily_topic():
    try:
        email = auth_service.get_user_email()
        if not email:
            raise HTTPException(401, "로그인이 필요합니다.")

        supabase_url, headers = _supabase_headers()
        if not supabase_url:
            raise HTTPException(500, "Supabase 설정 누락")

        _disable_insecure_warnings()
        url = (
            f"{supabase_url}/rest/v1/topics_queue"
            f"?assigned_employee_email=eq.{email}&status=eq.pending&order=created_at.asc&limit=1"
        )
        r = requests.get(url, headers=headers, timeout=5, verify=False, proxies={"http": None, "https": None})

        if r.status_code != 200:
            raise HTTPException(500, f"Supabase 호출 오류: {r.text}")

        data = r.json()
        if not data:
            return {"status": "error", "error": "배정 대기 중인 오늘의 주제가 없습니다."}

        item = data[0]
        topic_id = item["id"]
        topic_name = item["topic"]
        category_id = item.get("category_id")
        category_script_style = None
        category_image_style = None
        category_row = None
        category_video_type = "longform"
        assigned_language = _normalize_content_language(item.get("language"))
        policy = _fetch_longform_policy(supabase_url, headers)
        min_duration_minutes = max(15, _to_int(policy.get("sys_api_longform_min_duration_minutes"), 15))
        assigned_duration_minutes = max(
            min_duration_minutes,
            _to_int(
                item.get("assigned_duration_minutes")
                or item.get("recommended_duration_minutes"),
                min_duration_minutes,
            ),
        )
        estimated_payout = _calculate_longform_payout(assigned_duration_minutes, policy)
        duration_locked = str(item.get("duration_locked", policy.get("sys_api_longform_duration_lock_enabled", "true"))).lower() not in ("false", "0", "none")

        if category_id:
            try:
                cat_url = f"{supabase_url}/rest/v1/categories?id=eq.{category_id}"
                cat_r = requests.get(cat_url, headers=headers, timeout=5, verify=False, proxies={"http": None, "https": None})
                if cat_r.status_code == 200:
                    cat_data = cat_r.json()
                    if cat_data:
                        category_row = cat_data[0]
                        category_video_type = category_row.get("video_type") or "longform"
                        assigned_language = _normalize_content_language(item.get("language") or category_row.get("language"))
                        category_script_style = category_row.get("default_script_style")
                        category_image_style = category_row.get("default_image_style")
            except Exception as e:
                print(f"[Queue API Warning] Failed to fetch category default styles: {e}")

        # AI가 주제에 맞게 배정한 스타일을 우선 사용하고, 없으면 카테고리 기본 스타일로 폴백한다.
        assigned_script_style = item.get("assigned_script_style") or category_script_style
        assigned_image_style = item.get("assigned_image_style") or category_image_style

        update_url = f"{supabase_url}/rest/v1/topics_queue?id=eq.{topic_id}"
        patch_headers = headers.copy()
        patch_headers["Prefer"] = "return=representation"
        r_update = requests.patch(
            update_url,
            headers=patch_headers,
            json={"status": "assigned"},
            timeout=5,
            verify=False,
            proxies={"http": None, "https": None},
        )
        if r_update.status_code != 200:
            print(f"[Queue] Failed to update topic status in Supabase: {r_update.text}")

        project_id = db.create_project(
            name=topic_name,
            topic=topic_name,
            app_mode=category_video_type,
            language=assigned_language,
            employee_email=email,
            script_style=assigned_script_style,
            image_style=assigned_image_style,
        )

        if category_row:
            _apply_category_upload_channel(project_id, category_row)

        db.update_project_setting(project_id, "topic_queue_id", topic_id)
        db.update_project_setting(project_id, "topic_queue_category_id", category_id or "")
        db.update_project_setting(project_id, "target_language", assigned_language)
        # AI가 정한 스타일을 워커가 임의로 바꾸지 못하도록 잠근다.
        db.update_project_setting(project_id, "style_locked", "1")
        if category_video_type == "longform":
            db.update_project_setting(project_id, "duration_seconds", assigned_duration_minutes * 60)
            db.update_project_setting(project_id, "assigned_duration_minutes", assigned_duration_minutes)
            db.update_project_setting(project_id, "assigned_duration_seconds", assigned_duration_minutes * 60)
            db.update_project_setting(project_id, "duration_locked", "1" if duration_locked else "0")
            db.update_project_setting(project_id, "estimated_payout", estimated_payout)
            db.update_project_setting(project_id, "duration_reason", item.get("duration_reason") or "")
            db.update_project_setting(project_id, "difficulty_level", item.get("difficulty_level") or "")
            db.update_project_setting(project_id, "payout_policy_json", json.dumps({
                "min_duration_minutes": min_duration_minutes,
                "base_payout": _to_float(policy.get("sys_api_longform_base_payout"), 4.0),
                "extra_minute_payout": _to_float(policy.get("sys_api_longform_extra_minute_payout"), 0.0),
            }, ensure_ascii=False))
        try:
            sync_topic_progress(project_id, topic_id)
        except Exception as sync_err:
            print(f"[Queue API Warning] Failed to sync initial topic progress: {sync_err}")

        return {"status": "success", "project_id": project_id, "topic": topic_name, "language": assigned_language}
    except HTTPException:
        raise
    except Exception as e:
        print(f"[Queue API Error] {e}")
        return {"status": "error", "error": str(e)}
