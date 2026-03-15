from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import RedirectResponse, HTMLResponse
from pydantic import BaseModel
from typing import List
from services.blog_service import blog_service
from config import config
import database as db
import httpx
from urllib.parse import urlencode

router = APIRouter(prefix="/api/blog", tags=["Blog"])

BLOGGER_SCOPES = "https://www.googleapis.com/auth/blogger"
REDIRECT_URI = "http://127.0.0.1:8000/api/blog/oauth/callback"


class BlogGenerateRequest(BaseModel):
    source_type: str
    source_value: str
    platform: str = "wordpress"
    blog_style: str = "review"
    language: str = "ko"
    user_notes: str = ""


class BlogPostRequest(BaseModel):
    title: str
    content: str
    tags: List[str] = []
    platforms: List[str] = ["wordpress"]


@router.post("/generate")
async def generate_blog(req: BlogGenerateRequest):
    """AI 블로그 콘텐츠 생성"""
    try:
        result = await blog_service.generate_blog_from_source(
            source_type=req.source_type,
            source_value=req.source_value,
            platform=req.platform,
            blog_style=req.blog_style,
            language=req.language,
            user_notes=req.user_notes
        )
        return result
    except Exception as e:
        print(f"Blog generate error: {e}")
        return {"status": "error", "error": str(e)}


@router.post("/post")
async def post_blog(req: BlogPostRequest):
    """블로그 게시 (워드프레스/Blogger 동시 지원)"""
    results = {}
    platforms = req.platforms or ["wordpress"]

    for platform in platforms:
        try:
            if platform == "wordpress":
                res = await blog_service.post_to_wordpress(
                    title=req.title, content=req.content, tags=req.tags
                )
                results["wordpress"] = res
            elif platform == "blogger":
                res = await blog_service.post_to_blogger(
                    title=req.title, content=req.content, tags=req.tags
                )
                results["blogger"] = res
            else:
                results[platform] = {"status": "error", "error": f"지원하지 않는 플랫폼: {platform}"}
        except Exception as e:
            results[platform] = {"status": "error", "error": str(e)}

    all_ok = all(r.get("status") == "ok" for r in results.values())
    any_ok = any(r.get("status") == "ok" for r in results.values())

    return {
        "status": "ok" if all_ok else ("partial" if any_ok else "error"),
        "results": results
    }


# =============================================
# Google Blogger OAuth2 인증 플로우
# =============================================

@router.get("/oauth/start")
async def blogger_oauth_start():
    """구글 블로그 OAuth2 인증 시작 - Google 로그인 페이지로 리다이렉트"""
    client_id = config.BLOG_CLIENT_ID or db.get_global_setting("blog_client_id", "")
    if not client_id:
        raise HTTPException(400, "Google Blog Client ID가 설정되지 않았습니다.")

    params = urlencode({
        "client_id": client_id,
        "redirect_uri": REDIRECT_URI,
        "response_type": "code",
        "scope": BLOGGER_SCOPES,
        "access_type": "offline",
        "prompt": "consent",
    })
    auth_url = f"https://accounts.google.com/o/oauth2/v2/auth?{params}"
    return RedirectResponse(url=auth_url)


@router.get("/oauth/callback")
async def blogger_oauth_callback(request: Request):
    """Google OAuth2 콜백 - authorization code를 token으로 교환"""
    code = request.query_params.get("code")
    error = request.query_params.get("error")

    if error:
        return HTMLResponse(f"""
        <html><body style="background:#0f172a;color:#f87171;font-family:sans-serif;display:flex;align-items:center;justify-content:center;height:100vh;">
        <div style="text-align:center;">
            <h2>인증 실패</h2>
            <p>{error}</p>
            <p><a href="/settings" style="color:#60a5fa;">설정으로 돌아가기</a></p>
        </div></body></html>
        """)

    if not code:
        return HTMLResponse("<h2>인증 코드가 없습니다.</h2>")

    client_id = config.BLOG_CLIENT_ID or db.get_global_setting("blog_client_id", "")
    client_secret = config.BLOG_CLIENT_SECRET or db.get_global_setting("blog_client_secret", "")

    # Authorization code → Access Token + Refresh Token 교환
    async with httpx.AsyncClient() as client:
        res = await client.post("https://oauth2.googleapis.com/token", data={
            "code": code,
            "client_id": client_id,
            "client_secret": client_secret,
            "redirect_uri": REDIRECT_URI,
            "grant_type": "authorization_code"
        })

    if res.status_code != 200:
        return HTMLResponse(f"""
        <html><body style="background:#0f172a;color:#f87171;font-family:sans-serif;display:flex;align-items:center;justify-content:center;height:100vh;">
        <div style="text-align:center;">
            <h2>토큰 교환 실패</h2>
            <p>{res.text}</p>
            <p><a href="/settings" style="color:#60a5fa;">설정으로 돌아가기</a></p>
        </div></body></html>
        """)

    token_data = res.json()
    refresh_token = token_data.get("refresh_token", "")

    if refresh_token:
        # DB에 refresh_token 저장
        db.save_global_setting("blog_refresh_token", refresh_token)
        print(f"[Blogger OAuth] Refresh token saved successfully")

    return HTMLResponse(f"""
    <html><body style="background:#0f172a;color:#10b981;font-family:sans-serif;display:flex;align-items:center;justify-content:center;height:100vh;">
    <div style="text-align:center;">
        <h1 style="font-size:48px;margin-bottom:20px;">✅</h1>
        <h2>구글 블로그 연동 완료!</h2>
        <p style="color:#94a3b8;margin-top:10px;">이제 블로그 자동화 페이지에서 구글 블로그에 게시할 수 있습니다.</p>
        <p style="margin-top:20px;"><a href="/settings" style="color:#60a5fa;text-decoration:none;padding:10px 20px;border:1px solid #60a5fa;border-radius:8px;">설정으로 돌아가기</a></p>
    </div></body></html>
    """)


@router.get("/oauth/status")
async def blogger_oauth_status():
    """구글 블로그 OAuth 연동 상태 확인"""
    refresh_token = db.get_global_setting("blog_refresh_token", "")
    has_token = bool(refresh_token)

    if has_token:
        # 토큰이 유효한지 테스트
        client_id = config.BLOG_CLIENT_ID or db.get_global_setting("blog_client_id", "")
        client_secret = config.BLOG_CLIENT_SECRET or db.get_global_setting("blog_client_secret", "")
        if client_id and client_secret:
            try:
                async with httpx.AsyncClient() as client:
                    res = await client.post("https://oauth2.googleapis.com/token", data={
                        "client_id": client_id,
                        "client_secret": client_secret,
                        "refresh_token": refresh_token,
                        "grant_type": "refresh_token"
                    })
                    if res.status_code == 200:
                        return {"status": "ok", "connected": True, "message": "구글 블로그 연동됨"}
                    else:
                        return {"status": "ok", "connected": False, "message": "토큰 만료 - 재인증 필요"}
            except Exception:
                pass

    return {"status": "ok", "connected": False, "message": "연동되지 않음 - OAuth 인증 필요"}
