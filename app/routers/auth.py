import json
import os

import requests
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel

import database as db
from services.app_state import get_templates
from services.auth_service import auth_service
from services.topic_queue_sync_service import sync_topic_progress
from services.web_admin_client import web_admin_client


router = APIRouter(tags=["Auth"])


class LoginRequest(BaseModel):
    email: str
    pin_code: str


class RegisterRequest(BaseModel):
    full_name: str
    contact: str
    email: str
    nationality: str
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


def _apply_category_upload_channel(project_id: int, category_row: dict):
    """移댄뀒怨좊━??怨좎젙???낅줈??梨꾨꼸???덉쑝硫??꾨줈?앺듃 ?ㅼ젙??諛섏쁺"""
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


def _calculate_longform_payout(minutes: int, policy: dict) -> int:
    min_minutes = max(15, _to_int(policy.get("sys_api_longform_min_duration_minutes"), 15))
    base_pay = max(0, _to_int(policy.get("sys_api_longform_base_payout"), 10000))
    extra_pay = max(0, _to_int(policy.get("sys_api_longform_extra_minute_payout"), 500))
    return base_pay + max(0, minutes - min_minutes) * extra_pay


def _fetch_longform_policy(supabase_url: str, headers: dict) -> dict:
    defaults = {
        "sys_api_longform_min_duration_minutes": "15",
        "sys_api_longform_base_payout": "10000",
        "sys_api_longform_extra_minute_payout": "500",
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


@router.get("/api/auth/signup-options")
async def get_signup_options():
    try:
        categories = web_admin_client.fetch_categories(select="id,name,video_type")
        normalized_categories = []
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

        return {
            "categories": normalized_categories,
            "duration_options": [
                {"value": "15m", "label": "15 min"},
                {"value": "30m", "label": "30 min"},
                {"value": "60m_plus", "label": "60+ min"},
            ],
        }
    except Exception as e:
        print(f"[API] Failed to fetch signup options: {e}")
        return {"categories": [], "duration_options": []}


@router.post("/api/auth/register")
async def post_auth_register(req: RegisterRequest):
    try:
        if not web_admin_client.has_supabase():
            return {"success": False, "error": "서버 DB 연동 설정이 누락되었습니다."}

        full_name = req.full_name.strip()
        contact = req.contact.strip()
        email = req.email.strip().lower()
        nationality = req.nationality.strip()
        preferred_video_length = str(req.preferred_video_length or "").strip()
        requested_category_ids = [str(item).strip() for item in (req.preferred_category_ids or []) if str(item).strip()]
        if not all([full_name, contact, email, nationality]):
            return {"success": False, "error": "이름, 연락처, 이메일, 국적은 모두 입력해야 합니다."}
        if "@" not in email or "." not in email:
            return {"success": False, "error": "이메일 형식이 올바르지 않습니다."}
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
        import random
        my_referral_code = str(random.randint(100000, 999999))
        
        return web_admin_client.submit_worker_registration({
            "full_name": full_name,
            "contact": contact,
            "email": email,
            "nationality": nationality,
            "terms_accepted_at": now,
            "privacy_accepted_at": now,
            "my_referral_code": my_referral_code,
            "referred_by_code": req.referral_code.strip() if req.referral_code else "",
            "preferred_category_ids": preferred_category_ids,
            "preferred_category_names": preferred_category_names,
            "preferred_video_length": preferred_video_length,
        })
    except Exception as e:
        return {"success": False, "error": f"가입 신청 오류: {str(e)}"}


@router.post("/api/auth/login")
async def post_auth_login(req: LoginRequest):
    try:
        if not web_admin_client.has_supabase():
            return {"success": False, "error": "서버 DB 연동 설정이 누락되었습니다."}

        profile = web_admin_client.fetch_profile_by_email(req.email)
        if profile:
            # [WHITELIST SECURITY CHECK]
            # profiles 테이블의 is_approved 컬럼 검증 (True 또는 'approved' 상태만 로그인 허용)
            is_approved = profile.get("is_approved")
            # is_approved 컬럼이 없거나 명시적으로 False인 경우 차단
            if is_approved is False or is_approved is None or str(is_approved).lower() in ("false", "0", "none"):
                return {"success": False, "error": "어드민 승인 대기 중이거나 비활성화된 계정입니다."}

            db_pin = str(profile.get("pin_code") or "").strip()
            input_pin = str(req.pin_code).strip()

            if db_pin == input_pin:
                auth_service.login_user(req.email)
                response = JSONResponse({"success": True})
                response.set_cookie(
                    key="user_email",
                    value=req.email,
                    max_age=30 * 24 * 60 * 60,
                    httponly=False,
                )
                return response

            return {"success": False, "error": "PIN 번호가 일치하지 않습니다."}

        return {"success": False, "error": "등록되지 않은 직원 이메일입니다."}
    except Exception as e:
        return {"success": False, "error": f"로그인 오류: {str(e)}"}


@router.post("/api/auth/logout")
async def post_auth_logout():
    auth_service.logout_user()
    response = JSONResponse({"success": True})
    response.delete_cookie("user_email")
    return response


@router.post("/api/auth/sync")
async def sync_auth():
    try:
        email = auth_service.get_user_email()
        if email:
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
                }

            return {"success": False, "error": "Supabase ?숆린???ㅽ뙣"}

        success = auth_service.verify_license()

        if success:
            return {
                "success": True,
                "membership": auth_service.get_membership(),
                "token_balance": auth_service.get_token_balance(),
            }
        return {"success": False, "error": "Verification failed"}
    except Exception as e:
        return {"success": False, "error": str(e)}


@router.post("/api/topics/get-daily")
async def get_daily_topic():
    try:
        email = auth_service.get_user_email()
        if not email:
            raise HTTPException(401, "濡쒓렇?몄씠 ?꾩슂?⑸땲??")

        supabase_url, headers = _supabase_headers()
        if not supabase_url:
            raise HTTPException(500, "Supabase ?ㅼ젙 ?꾨씫")

        _disable_insecure_warnings()
        url = (
            f"{supabase_url}/rest/v1/topics_queue"
            f"?assigned_employee_email=eq.{email}&status=eq.pending&order=created_at.asc&limit=1"
        )
        r = requests.get(url, headers=headers, timeout=5, verify=False, proxies={"http": None, "https": None})

        if r.status_code != 200:
            raise HTTPException(500, f"Supabase ?몄텧 ?ㅻ쪟: {r.text}")

        data = r.json()
        if not data:
            return {"status": "error", "error": "諛곗젙 ?湲?以묒씤 ?ㅻ뒛??二쇱젣媛 ?놁뒿?덈떎."}

        item = data[0]
        topic_id = item["id"]
        topic_name = item["topic"]
        category_id = item.get("category_id")
        category_script_style = None
        category_image_style = None
        category_row = None
        category_video_type = "longform"
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
        estimated_payout = _to_int(
            item.get("estimated_payout"),
            _calculate_longform_payout(assigned_duration_minutes, policy),
        )
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
                        category_script_style = category_row.get("default_script_style")
                        category_image_style = category_row.get("default_image_style")
            except Exception as e:
                print(f"[Queue API Warning] Failed to fetch category default styles: {e}")

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
            language="ko",
            employee_email=email,
            script_style=category_script_style,
            image_style=category_image_style,
        )

        if category_row:
            _apply_category_upload_channel(project_id, category_row)

        db.update_project_setting(project_id, "topic_queue_id", topic_id)
        db.update_project_setting(project_id, "topic_queue_category_id", category_id or "")
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
                "base_payout": _to_int(policy.get("sys_api_longform_base_payout"), 10000),
                "extra_minute_payout": _to_int(policy.get("sys_api_longform_extra_minute_payout"), 500),
            }, ensure_ascii=False))
        try:
            sync_topic_progress(project_id, topic_id)
        except Exception as sync_err:
            print(f"[Queue API Warning] Failed to sync initial topic progress: {sync_err}")

        return {"status": "success", "project_id": project_id, "topic": topic_name}
    except Exception as e:
        print(f"[Queue API Error] {e}")
        return {"status": "error", "error": str(e)}
