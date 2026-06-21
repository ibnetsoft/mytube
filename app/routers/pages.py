"""
?섏씠吏 ?쇱슦????HTML ?쒗뵆由??묐떟 ?꾩슜
templates ?몄뒪?댁뒪??main.py?먯꽌 二쇱엯 (?쒗솚 import 諛⑹?)
"""
from fastapi import APIRouter, Request, Query
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from typing import Optional
import database as db

router = APIRouter(tags=["Pages"])

# main.py?먯꽌 init_pages(templates) ?몄텧 ??二쇱엯
_templates: Optional[Jinja2Templates] = None

def init_pages(templates: Jinja2Templates):
    global _templates
    _templates = templates

def _render(request, template, page, title, **extra):
    from services.auth_service import auth_service
    return _templates.TemplateResponse(
        request=request,
        name=template,
        context={
            "page": page,
            "title": title,
            "membership": auth_service.get_membership(),
            "token_balance": auth_service.get_token_balance(),
            **extra
        }
    )

@router.get("/", response_class=HTMLResponse)
async def page_index(request: Request):
    return _render(request, "pages/topic.html", "topic", "주제 찾기")

@router.get("/projects", response_class=HTMLResponse)
async def page_projects(request: Request):
    return _render(request, "pages/projects.html", "projects", "프로젝트")

@router.get("/script-plan", response_class=HTMLResponse)
async def page_script_plan(request: Request):
    app_mode = db.get_global_setting("app_mode", "longform")
    if app_mode == "longform_music":
        return RedirectResponse(url="/music-plan", status_code=302)
    return _render(request, "pages/script_plan.html", "script-plan", "대본 기획")

@router.get("/music-plan", response_class=HTMLResponse)
async def page_music_plan(request: Request):
    return _render(request, "pages/music_plan.html", "music-plan", "음악 기획")

@router.get("/script-gen", response_class=HTMLResponse)
async def page_script_gen(request: Request, project_id: Optional[int] = Query(None)):
    project = None
    if project_id:
        project = db.get_project(project_id)
    return _render(request, "pages/script_gen.html", "script-gen", "대본 생성", project=project)

@router.get("/image-gen", response_class=HTMLResponse)
async def page_image_gen(request: Request):
    app_mode = db.get_global_setting("app_mode", "longform")
    if app_mode == "longform_music":
        return _render(request, "pages/music_cover.html", "image-gen", "커버 이미지")
    return _render(request, "pages/image_gen.html", "image-gen", "이미지 생성")

@router.get("/image-crop", response_class=HTMLResponse)
async def page_image_crop(request: Request):
    return _render(request, "pages/image_crop.html", "image-crop", "이미지 자르기")

@router.get("/audio-gen", response_class=HTMLResponse)
async def page_audio_gen(request: Request):
    app_mode = db.get_global_setting("app_mode", "longform")
    if app_mode == "longform_music":
        return _render(request, "pages/music_tracks.html", "audio-gen", "트랙 관리")
    return _render(request, "pages/audio_gen.html", "audio-gen", "오디오 생성")

@router.get("/video-gen", response_class=HTMLResponse)
async def page_video_gen(request: Request):
    return _render(request, "pages/video_gen.html", "video-gen", "영상 생성")

@router.get("/tts", response_class=HTMLResponse)
async def page_tts(request: Request):
    return _render(request, "pages/tts.html", "tts", "TTS 생성")

@router.get("/render", response_class=HTMLResponse)
async def page_render(request: Request):
    app_mode = db.get_global_setting("app_mode", "longform")
    if app_mode == "longform_music":
        return _render(request, "pages/music_render.html", "render", "렌더링")
    return _render(request, "pages/render.html", "render", "영상 렌더링")

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
                "title": "예약 업로드",
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
            "title": "영상 업로드",
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
            "title": "자막 편집",
            "project": project,
            "membership": auth_service.get_membership(),
            "token_balance": auth_service.get_token_balance()
        }
    )

@router.get("/title-desc", response_class=HTMLResponse)
async def page_title_desc(request: Request):
    app_mode = db.get_global_setting("app_mode", "longform")
    if app_mode == "longform_music":
        return _render(request, "pages/music_title_desc.html", "title-desc", "제목/설명 생성")
    return _render(request, "pages/title_desc.html", "title-desc", "제목/설명 생성")

@router.get("/thumbnail", response_class=HTMLResponse)
async def page_thumbnail(request: Request, project_id: Optional[int] = Query(None)):
    app_mode = db.get_global_setting("app_mode", "longform")
    return _render(request, "pages/thumbnail.html", "thumbnail", "썸네일 생성", project_id=project_id, app_mode=app_mode)

@router.get("/template", response_class=HTMLResponse)
async def page_template(request: Request, project_id: Optional[int] = Query(None)):
    app_mode = db.get_global_setting("app_mode", "longform")
    return _render(request, "pages/template.html", "template", "템플릿", project_id=project_id, app_mode=app_mode)

@router.get("/shorts", response_class=HTMLResponse)
async def page_shorts(request: Request):
    return _render(request, "pages/shorts.html", "shorts", "쇼츠 생성")

@router.get("/commerce-shorts", response_class=HTMLResponse)
async def page_commerce_shorts(request: Request):
    return _render(request, "pages/commerce_shorts.html", "commerce-shorts", "커머스 쇼츠")

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
            "title": "설정",
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
    return _render(request, "pages/logs.html", "logs", "로그")

@router.get("/autopilot", response_class=HTMLResponse)
async def page_autopilot(request: Request):
    return _render(request, "pages/autopilot.html", "autopilot", "오토파일럿")

