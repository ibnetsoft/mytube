"""
페이지 라우터 — HTML 템플릿 응답 전용
templates 인스턴스는 main.py에서 주입 (순환 import 방지)
"""
from fastapi import APIRouter, Request, Query
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from typing import Optional
import database as db

router = APIRouter(tags=["Pages"])

# main.py에서 init_pages(templates) 호출 시 주입
_templates: Optional[Jinja2Templates] = None

def init_pages(templates: Jinja2Templates):
    global _templates
    _templates = templates

def _render(request, template, page, title, **extra):
    return _templates.TemplateResponse(template, {
        "request": request,
        "page": page,
        "title": title,
        **extra
    })

@router.get("/", response_class=HTMLResponse)
async def page_index(request: Request):
    return _render(request, "pages/topic.html", "topic", "주제 찾기")

@router.get("/projects", response_class=HTMLResponse)
async def page_projects(request: Request):
    return _render(request, "pages/projects.html", "projects", "내 프로젝트")

@router.get("/script-plan", response_class=HTMLResponse)
async def page_script_plan(request: Request):
    return _render(request, "pages/script_plan.html", "script-plan", "대본 기획")

@router.get("/script-gen", response_class=HTMLResponse)
async def page_script_gen(request: Request):
    return _render(request, "pages/script_gen.html", "script-gen", "대본 생성")

@router.get("/image-gen", response_class=HTMLResponse)
async def page_image_gen(request: Request):
    return _render(request, "pages/image_gen.html", "image-gen", "이미지 생성")

@router.get("/audio-gen", response_class=HTMLResponse)
async def page_audio_gen(request: Request):
    return _render(request, "pages/audio_gen.html", "audio-gen", "오디오 생성")

@router.get("/video-gen", response_class=HTMLResponse)
async def page_video_gen(request: Request):
    return _render(request, "pages/video_gen.html", "video-gen", "동영상 생성")

@router.get("/tts", response_class=HTMLResponse)
async def page_tts(request: Request):
    return _render(request, "pages/tts.html", "tts", "TTS 생성")

@router.get("/render", response_class=HTMLResponse)
async def page_render(request: Request):
    return _render(request, "pages/render.html", "render", "영상 렌더링")

@router.get("/video-upload", response_class=HTMLResponse)
async def page_video_upload(request: Request):
    from services.auth_service import auth_service
    return _templates.TemplateResponse("pages/video_upload.html", {
        "request": request,
        "page": "video-upload",
        "title": "영상 업로드",
        "is_independent": auth_service.is_independent()
    })

@router.get("/subtitle_gen", response_class=HTMLResponse)
@router.get("/subtitle-gen", response_class=HTMLResponse)
async def page_subtitle_gen(request: Request, project_id: Optional[int] = Query(None)):
    project = None
    if project_id:
        project = db.get_project(project_id)
    # project_id 없으면 JS의 getCurrentProject() / localStorage 우선순위에 맡김
    return _templates.TemplateResponse("pages/subtitle_gen.html", {
        "request": request,
        "page": "subtitle-gen",
        "title": "자막 편집",
        "project": project
    })

@router.get("/title-desc", response_class=HTMLResponse)
async def page_title_desc(request: Request):
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
    return _render(request, "pages/settings.html", "settings", "설정")

@router.get("/logs", response_class=HTMLResponse)
async def page_logs(request: Request):
    return _render(request, "pages/logs.html", "logs", "로그")

@router.get("/autopilot", response_class=HTMLResponse)
async def page_autopilot(request: Request):
    return _render(request, "pages/autopilot.html", "autopilot", "오토파일럿")
