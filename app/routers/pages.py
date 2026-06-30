"""
페이지 라우터와 HTML 템플릿 응답 전용.
templates 인스턴스는 main.py에서 주입한다 (순환 import 방지).
"""
from fastapi import APIRouter, Request, Query
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from typing import Optional
import database as db
from app.modes import DEFAULT_APP_MODE, normalize_app_mode

router = APIRouter(tags=["Pages"])

# main.py에서 init_pages(templates) 호출 시 주입
_templates: Optional[Jinja2Templates] = None

def init_pages(templates: Jinja2Templates):
    global _templates
    _templates = templates


def _resolve_page_mode(project_id: Optional[int] = None) -> str:
    if project_id:
        settings = db.get_project_settings(project_id) or {}
        project_mode = settings.get("app_mode")
        if not project_mode:
            project = db.get_project(project_id) or {}
            project_mode = project.get("app_mode")
        if project_mode:
            return normalize_app_mode(project_mode, DEFAULT_APP_MODE)
    return normalize_app_mode(db.get_global_setting("app_mode", DEFAULT_APP_MODE), DEFAULT_APP_MODE)


def _is_standard_membership() -> bool:
    from services.auth_service import auth_service
    membership = (auth_service.get_membership() or "std").strip().lower()
    return membership in ("std", "standard")


def _route_with_project_id(base_path: str, project_id: Optional[int]) -> str:
    if project_id:
        return f"{base_path}?project_id={project_id}"
    return base_path

def _render(request, template, page, title, **extra):
    from services.auth_service import auth_service
    email = auth_service.get_user_email()
    is_admin = db.is_user_admin(email) if email else False
    return _templates.TemplateResponse(
        request=request,
        name=template,
        context={
            "page": page,
            "title": title,
            "membership": auth_service.get_membership(),
            "token_balance": auth_service.get_token_balance(),
            "is_admin": is_admin,
            **extra
        }
    )

@router.get("/", response_class=HTMLResponse)
async def page_index(request: Request):
    return RedirectResponse(url="/projects", status_code=302)

@router.get("/projects", response_class=HTMLResponse)
async def page_projects(request: Request, view: Optional[str] = Query("topics")):
    view_mode = "projects" if view == "projects" else "topics"
    return _render(
        request,
        "pages/projects.html",
        "projects",
        "nav_topic" if view_mode == "topics" else "nav_my_projects",
        view_mode=view_mode,
    )

@router.get("/script-plan", response_class=HTMLResponse)
async def page_script_plan(request: Request, project_id: Optional[int] = Query(None)):
    app_mode = _resolve_page_mode(project_id)
    if app_mode == "longform_music":
        return RedirectResponse(url=_route_with_project_id("/music-plan", project_id), status_code=302)
    return _render(
        request,
        "pages/script_plan.html",
        "script-plan",
        "nav_plan",
        app_mode=app_mode,
        project_id=project_id,
    )

@router.get("/music-plan", response_class=HTMLResponse)
async def page_music_plan(request: Request, project_id: Optional[int] = Query(None)):
    app_mode = _resolve_page_mode(project_id)
    if app_mode != "longform_music":
        fallback = _route_with_project_id("/script-plan", project_id) if project_id else "/projects"
        return RedirectResponse(url=fallback, status_code=302)
    if _is_standard_membership():
        return RedirectResponse(url="/projects", status_code=302)
    return _render(
        request,
        "pages/music_plan.html",
        "music-plan",
        "nav_music_plan",
        app_mode=app_mode,
        project_id=project_id,
    )

@router.get("/script-gen", response_class=HTMLResponse)
async def page_script_gen(request: Request, project_id: Optional[int] = Query(None)):
    project = None
    if project_id:
        project = db.get_project(project_id)
    return _render(request, "pages/script_gen.html", "script-gen", "nav_script", project=project)

@router.get("/image-gen", response_class=HTMLResponse)
async def page_image_gen(request: Request):
    app_mode = db.get_global_setting("app_mode", "longform")
    if app_mode == "longform_music":
        return _render(request, "pages/music_cover.html", "image-gen", "nav_cover_image")
    return _render(request, "pages/image_gen.html", "image-gen", "nav_image")

@router.get("/image-crop", response_class=HTMLResponse)
async def page_image_crop(request: Request):
    return _render(request, "pages/image_crop.html", "image-crop", "nav_image_crop")

@router.get("/audio-gen", response_class=HTMLResponse)
async def page_audio_gen(request: Request):
    app_mode = db.get_global_setting("app_mode", "longform")
    if app_mode == "longform_music":
        return _render(request, "pages/music_tracks.html", "audio-gen", "nav_track_generation")
    return _render(request, "pages/audio_gen.html", "audio-gen", "nav_audio")

@router.get("/video-gen", response_class=HTMLResponse)
async def page_video_gen(request: Request):
    return _render(request, "pages/video_gen.html", "video-gen", "nav_intro")

@router.get("/tts", response_class=HTMLResponse)
async def page_tts(request: Request):
    return _render(request, "pages/tts.html", "tts", "nav_tts")

@router.get("/render", response_class=HTMLResponse)
async def page_render(request: Request):
    app_mode = db.get_global_setting("app_mode", "longform")
    if app_mode == "longform_music":
        return _render(request, "pages/music_render.html", "render", "nav_render")
    return _render(request, "pages/render.html", "render", "nav_render")

@router.get("/video-upload", response_class=HTMLResponse)
async def page_video_upload(request: Request):
    from services.auth_service import auth_service
    membership = (auth_service.get_membership() or "std").lower()
    if membership in ("std", "standard"):
        return RedirectResponse(url="/projects")
    app_mode = db.get_global_setting("app_mode", "longform")
    if app_mode == "longform_music":
        return _templates.TemplateResponse(
            request=request,
            name="pages/music_video_upload.html",
            context={
                "page": "video-upload",
                "title": "nav_reserve",
                "is_independent": auth_service.is_independent(),
                "membership": auth_service.get_membership(),
                "token_balance": auth_service.get_token_balance()
            }
        )
    return _templates.TemplateResponse(
        request=request,
        name="pages/video_upload.html",
        context={
            "page": "video-upload",
            "title": "nav_upload",
            "is_independent": auth_service.is_independent(),
            "membership": auth_service.get_membership(),
            "token_balance": auth_service.get_token_balance()
        }
    )

@router.get("/subtitle_gen", response_class=HTMLResponse)
@router.get("/subtitle-gen", response_class=HTMLResponse)
async def page_subtitle_gen(request: Request, project_id: Optional[int] = Query(None)):
    project = None
    if project_id:
        project = db.get_project(project_id)
    from services.auth_service import auth_service
    return _templates.TemplateResponse(
        request=request,
        name="pages/subtitle_gen.html",
        context={
            "page": "subtitle-gen",
            "title": "nav_subtitle",
            "project": project,
            "membership": auth_service.get_membership(),
            "token_balance": auth_service.get_token_balance()
        }
    )

@router.get("/title-desc", response_class=HTMLResponse)
async def page_title_desc(request: Request):
    app_mode = db.get_global_setting("app_mode", "longform")
    if app_mode == "longform_music":
        return _render(request, "pages/music_title_desc.html", "title-desc", "nav_title_desc")
    return _render(request, "pages/title_desc.html", "title-desc", "nav_title_desc")

@router.get("/thumbnail", response_class=HTMLResponse)
async def page_thumbnail(request: Request, project_id: Optional[int] = Query(None)):
    app_mode = db.get_global_setting("app_mode", "longform")
    return _render(request, "pages/thumbnail.html", "thumbnail", "nav_thumbnail", project_id=project_id, app_mode=app_mode)

@router.get("/template", response_class=HTMLResponse)
async def page_template(request: Request, project_id: Optional[int] = Query(None)):
    app_mode = db.get_global_setting("app_mode", "longform")
    return _render(request, "pages/template.html", "template", "nav_shorts_template", project_id=project_id, app_mode=app_mode)

@router.get("/shorts", response_class=HTMLResponse)
async def page_shorts(request: Request):
    return _render(request, "pages/shorts.html", "shorts", "nav_shorts")

@router.get("/commerce-shorts", response_class=HTMLResponse)
async def page_commerce_shorts(request: Request):
    return _render(request, "pages/commerce_shorts.html", "commerce-shorts", "nav_commerce_shorts")

@router.get("/scene-split", response_class=HTMLResponse)
async def page_scene_split(request: Request, project_id: Optional[int] = Query(None)):
    app_mode = _resolve_page_mode(project_id)
    if _is_standard_membership():
        return RedirectResponse(url="/projects", status_code=302)
    return _render(
        request,
        "pages/scene_split.html",
        "scene-split",
        "nav_plan",
        app_mode=app_mode,
        project_id=project_id,
    )


@router.get("/video-prompts", response_class=HTMLResponse)
async def page_video_prompts(request: Request, project_id: Optional[int] = Query(None)):
    app_mode = _resolve_page_mode(project_id)
    if _is_standard_membership():
        return RedirectResponse(url="/projects", status_code=302)
    return _render(
        request,
        "pages/video_prompts.html",
        "video-prompts",
        "nav_intro",
        app_mode=app_mode,
        project_id=project_id,
    )


@router.get("/asset-upload", response_class=HTMLResponse)
async def page_asset_upload(request: Request, project_id: Optional[int] = Query(None)):
    app_mode = _resolve_page_mode(project_id)
    if _is_standard_membership():
        return RedirectResponse(url="/projects", status_code=302)
    return _render(
        request,
        "pages/asset_upload.html",
        "asset-upload",
        "nav_image",
        app_mode=app_mode,
        project_id=project_id,
    )


@router.get("/settings", response_class=HTMLResponse)
async def page_settings(request: Request):
    from services.auth_service import auth_service
    import datetime
    auth_service.verify_license()
    
    return _templates.TemplateResponse(
        request=request,
        name="pages/settings.html",
        context={
            "page": "settings",
            "title": "nav_settings",
            "now": datetime.datetime.now(),
            "membership": auth_service.get_membership(),
            "token_balance": auth_service.get_token_balance(),
            "youtube_channel": auth_service.get_youtube_channel(),
                        "my_referral_code": auth_service.get_referral_code(),
            "wallet_info": auth_service.get_or_create_wallet_info(),
            "min_withdrawal_usdt": db.get_global_setting("min_withdrawal_usdt", "10"),
            "youtube_handle": auth_service.get_youtube_handle()
        }
    )

@router.get("/logs", response_class=HTMLResponse)
async def page_logs(request: Request):
    return _render(request, "pages/logs.html", "logs", "nav_logs")

@router.get("/autopilot", response_class=HTMLResponse)
async def page_autopilot(request: Request):
    return _render(request, "pages/autopilot.html", "autopilot", "nav_autopilot")

