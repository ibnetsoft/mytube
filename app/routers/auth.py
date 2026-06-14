import os

import requests
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel

import database as db
from services.app_state import get_templates
from services.auth_service import auth_service


router = APIRouter(tags=["Auth"])


class LoginRequest(BaseModel):
    email: str
    pin_code: str


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
        supabase_url, headers = _supabase_headers()
        if not supabase_url:
            return {"emails": []}

        _disable_insecure_warnings()
        url = f"{supabase_url}/rest/v1/profiles?select=email"
        r = requests.get(url, headers=headers, timeout=5, verify=False, proxies={"http": None, "https": None})
        if r.status_code == 200:
            emails = [item["email"] for item in r.json() if item.get("email")]
            return {"emails": emails}
        return {"emails": []}
    except Exception as e:
        print(f"[API] Failed to fetch emails: {e}")
        return {"emails": []}


@router.post("/api/auth/login")
async def post_auth_login(req: LoginRequest):
    try:
        supabase_url, headers = _supabase_headers()
        if not supabase_url:
            return {"success": False, "error": "서버 DB 연동 설정이 누락되었습니다."}

        _disable_insecure_warnings()
        url = f"{supabase_url}/rest/v1/profiles?email=eq.{req.email}&select=*"
        r = requests.get(url, headers=headers, timeout=5, verify=False, proxies={"http": None, "https": None})

        if r.status_code == 200:
            data = r.json()
            if data:
                profile = data[0]
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

        return {"success": False, "error": f"Supabase 연동 실패 (HTTP {r.status_code})"}
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
            supabase_url, headers = _supabase_headers()
            if supabase_url:
                _disable_insecure_warnings()
                url = f"{supabase_url}/rest/v1/profiles?email=eq.{email}&select=*"
                r = requests.get(url, headers=headers, timeout=5, verify=False, proxies={"http": None, "https": None})
                if r.status_code == 200:
                    data = r.json()
                    if data:
                        profile = data[0]
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

            return {"success": False, "error": "Supabase 동기화 실패"}

        success = auth_service.verify_license()
        if hasattr(success, "__await__") or hasattr(success, "cr_await"):
            success = await success

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

        if category_id:
            try:
                cat_url = f"{supabase_url}/rest/v1/categories?id=eq.{category_id}"
                cat_r = requests.get(cat_url, headers=headers, timeout=5, verify=False, proxies={"http": None, "https": None})
                if cat_r.status_code == 200:
                    cat_data = cat_r.json()
                    if cat_data:
                        category_script_style = cat_data[0].get("default_script_style")
                        category_image_style = cat_data[0].get("default_image_style")
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
            app_mode="longform",
            language="ko",
            employee_email=email,
            script_style=category_script_style,
            image_style=category_image_style,
        )

        return {"status": "success", "project_id": project_id, "topic": topic_name}
    except Exception as e:
        print(f"[Queue API Error] {e}")
        return {"status": "error", "error": str(e)}
