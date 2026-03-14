"""
PICADIRI STUDIO - FastAPI 메인 서버
YouTube 영상 자동화 제작 플랫폼 (Python 기반)
"""
import sys
import os
# Windows cp949 이모지 출력 크래시 방지 - 모든 서비스에 적용
if sys.stdout and hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

from fastapi import FastAPI, Request, HTTPException, Form, BackgroundTasks, Body, Query, UploadFile, File
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional, Dict, Any, Union
import uvicorn
import httpx
import time
import asyncio
import json
import re
import datetime
from pathlib import Path

# ==========================================
# FFmpeg & Pydub Configuration (Global)
# ==========================================
try:
    import imageio_ffmpeg
    from pydub import AudioSegment
    ffmpeg_path = imageio_ffmpeg.get_ffmpeg_exe()
    AudioSegment.converter = ffmpeg_path
    AudioSegment.ffmpeg = ffmpeg_path
    # Add to PATH so subprocess can find it if needed
    os.environ["PATH"] += os.pathsep + os.path.dirname(ffmpeg_path)
    print(f"[Main] FFmpeg configured: {ffmpeg_path}")
except Exception as e:
    print(f"[Main] FFmpeg setup warning: {e}")


from config import config
import database as db
from app.routers import settings  # [NEW]
from services.gemini_service import gemini_service
from services.replicate_service import replicate_service
from services.akool_service import akool_service
from services.auth_service import auth_service
from services.storage_service import storage_service
from services.thumbnail_service import thumbnail_service

# Helper: 프로젝트별 출력 폴더 생성
def get_project_output_dir(project_id: int):
    """
    프로젝트 ID를 기반으로 '프로젝트명_날짜' 형식의 폴더를 생성하고 경로를 반환합니다.
    """
    project = db.get_project(project_id)
    if not project:
        return config.OUTPUT_DIR, "/output" # Fallback

    # 폴더명 생성 (프로젝트명 + 생성일자 YYYYMMDD)
    # 안전한 파일명을 위해 공백/특수문자 처리
    safe_name = re.sub(r'[\\/*?:"<>|]', "", project['name']).strip().replace(" ", "_")
    
    # 날짜는 오늘 날짜 기준 (또는 프로젝트 생성일? 사용자 요청은 '날짜' 형식)
    # 보통 작업을 수행하는 '오늘' 날짜가 적절함.
    today = datetime.datetime.now().strftime("%Y%m%d")
    folder_name = f"{safe_name}_{today}"
    
    # 전체 경로
    abs_path = os.path.join(config.OUTPUT_DIR, folder_name)
    os.makedirs(abs_path, exist_ok=True)
    
    # 웹 접근 경로 (static mount 기준)
    # config.OUTPUT_DIR가 base이므로 relative path 필요
    web_path = f"/output/{folder_name}"
    
    return abs_path, web_path


# FastAPI 앱 생성
app = FastAPI(
    title="피카디리스튜디오",
    description="AI 기반 YouTube 영상 자동화 제작 플랫폼",
    version="2.0.0"
)

# CORS 설정
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 템플릿 및 정적 파일
templates = Jinja2Templates(directory=config.TEMPLATES_DIR)

# 업로드 파일 서빙
app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")

# i18n
from services.i18n import Translator
app_lang = os.environ.get("APP_LANG", "ko")
translator = Translator(app_lang)

# Add t function to Jinja2 globals
templates.env.globals['t'] = translator.t
templates.env.globals['current_lang'] = app_lang
templates.env.globals['membership'] = auth_service.get_membership()
templates.env.globals['is_independent'] = auth_service.is_independent()
def get_license_key():
    if os.path.exists("license.key"):
        with open("license.key", "r") as f:
            return f.read().strip()
    return ""

templates.env.globals['get_license_key'] = get_license_key
templates.env.globals['AUTH_SERVER_URL'] = "http://localhost:3000" if config.DEBUG else "https://mytube-ashy-seven.vercel.app"

# [NEW] Language Persistence - DB 우선, 파일 fallback
LANG_FILE = "language.pref"

def _load_saved_lang():
    """DB → 파일 순서로 저장된 언어를 읽어 translator에 적용"""
    global app_lang
    # 1. DB에서 읽기
    try:
        saved = db.get_global_setting("language", None)
        if saved and saved in ['ko', 'en', 'vi']:
            translator.set_lang(saved)
            app_lang = saved
            templates.env.globals['current_lang'] = app_lang
            print(f"[I18N] Loaded language from DB: {app_lang}")
            return
    except Exception:
        pass
    # 2. 파일에서 읽기 (fallback)
    if os.path.exists(LANG_FILE):
        with open(LANG_FILE, "r") as f:
            saved_lang = f.read().strip()
            if saved_lang in ['ko', 'en', 'vi']:
                translator.set_lang(saved_lang)
                app_lang = saved_lang
                templates.env.globals['current_lang'] = app_lang
                print(f"[I18N] Loaded language from file: {app_lang}")

_load_saved_lang()

# ✅ app_state에 실제 실행 중인 translator/templates 등록
# (settings.py 등 routers에서 'import main' 없이 참조 가능)
from services import app_state as _app_state
_app_state.register_translator(translator)
_app_state.register_templates(templates)

app.mount("/static", StaticFiles(directory=config.STATIC_DIR), name="static")

# Import Routers
from app.routers import autopilot as autopilot_router
from app.routers import video as video_router
from app.routers import commerce as commerce_router  # [NEW]
from app.routers import projects as projects_router # [NEW]
from app.routers import channels as channels_router # [NEW]
from app.routers import media as media_router # [NEW]
from app.routers import settings as settings_router # [NEW]
from app.routers import repository as repository_router # [NEW]
from app.routers import queue as queue_router # [NEW]
from app.routers import webtoon as webtoon_router # [NEW]
from app.routers import audio as audio_router # [NEW]
from app.routers import sources as sources_router # [NEW]

app.include_router(autopilot_router.router)
app.include_router(video_router.router)
app.include_router(commerce_router.router)  # [NEW]
app.include_router(projects_router.router) # [NEW]
app.include_router(channels_router.router) # [NEW]
app.include_router(media_router.router) # [NEW]
app.include_router(settings_router.router) # [NEW]
app.include_router(repository_router.router) # [NEW]
app.include_router(webtoon_router.router) # [NEW]
app.include_router(queue_router.router) # [NEW]
app.include_router(audio_router.router) # [NEW]
app.include_router(sources_router.router) # [NEW]


# output 폴더
os.makedirs(config.OUTPUT_DIR, exist_ok=True)
app.mount("/output", StaticFiles(directory=config.OUTPUT_DIR), name="output")

# uploads 폴더 (인트로 등 업로드용)
os.makedirs("uploads", exist_ok=True)
app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")

@app.on_event("startup")
async def startup_event():
    """앱 시작 시 실행 (DB 초기화 및 마이그레이션)"""
    try:
        # Verify License & Membership
        auth_service.verify_license()
        
        db.init_db()
        db.migrate_db()
        db.reset_rendering_status() # [FIX] Stuck rendering status reset
        
        # [NEW] Start Autopilot Batch Worker
        asyncio.create_task(autopilot_service.start_batch_worker())
        
        print(f"[Startup] DB Initialized. Membership: {auth_service.get_membership()}")
    except Exception as e:
        print(f"[Startup] Setup Failed: {e}")


# ===========================================
# Pydantic 모델
# ===========================================
from app.models.project import (
    ProjectCreate, ProjectUpdate, ProjectSettingUpdate, ProjectSettingsSave,
    StylePreset, AnalysisSave, ScriptStructureSave, ScriptSave,
    ImagePromptsSave, MetadataSave, ThumbnailsSave, ShortsSave,
    SubtitleDefaultSave
)
from app.models.media import (
    SearchRequest, GeminiRequest, TTSRequest, VideoRequest, PromptsGenerateRequest
)
from app.models.channel import ChannelCreate, ChannelResponse

# 스타일 매핑 
STYLE_PROMPTS = {
    "realistic": "A highly realistic photo, 8k resolution, highly detailed photography, lifelike textures, natural lighting, professional cinematography, high quality",
    "anime": "Anime style illustration, vibrant colors, detailed background, Makoto Shinkai style, high quality",
    "cinematic": "Cinematic movie shot, dramatic lighting, shadow and light depth, highly detailed, 4k",
    "minimal": "Minimalist flat vector illustration, simple shapes, clean lines, white background, high quality",
    "3d": "3D render, Pixar style, soft studio lighting, octane render, 4k, high quality",
    "k_webtoon": "Modern K-webtoon manhwa style, high-quality digital illustration, sharp line art, vibrant colors, expressive character, modern manhwa aesthetic, professional digital art, no text, no speech bubbles",
    "ghibli": "Studio Ghibli style, cel shaded, vibrant colors, lush background, Hayao Miyazaki style, highly detailed, masterfully painted",
    "k_manhwa": "A clean, high-quality, full-color webtoon style illustration in a 16:9 cinematic aspect ratio. Bold black outlines, flat graphic colors with soft gradients, clean vector-like finish. Isolated on a fully illustrated 16:9 detailed background. A cute, minimalist cartoon character with a perfectly uniform white circular head (solid white surface, no hair, shiny bald). THE FACE MUST HAVE a pair of distinct black eyes and a simple mouth. THE CHARACTER HAS EXACTLY TWO ARMS (one left arm, one right arm) AND EXACTLY TWO WHITE GLOVED HANDS TOTAL. NO THIRD ARM, NO FOURTH ARM, NO MULTIPLE LIMBS. NO REAR ARMS. The black limbs must have a perfectly uniform and consistent thickness. The character always wears a long-sleeved hooded sweatshirt (hoodie) that covers the arms down to the wrists, the hoodie is vibrant teal-blue (Brand Color: #00ADB5), black pants and simple sneakers. IMPORTANT: Background elements and other illustrated characters MUST NEVER overlap, touch, or be attached to the main character. The main character must be clearly separated from the background layers. ABSOLUTELY NO TEXT. NO HAIR. ONLY TWO ARMS AND TWO HANDS TOTAL. NO EXTRA LIMBS."
}




# ============ 학습 시스템 백그라운드 태스크 ============
async def background_learn_strategy(video_id: str, analysis_result: dict, script_style: str = "story"):
    """백그라운드에서 분석 결과를 기반으로 지식 추출 및 저장"""
    try:
        print(f"[Learning] Starting strategy extraction for video: {video_id}...")
        strategies = await gemini_service.extract_success_strategy(analysis_result)
        if strategies:
            for s in strategies:
                db.save_success_knowledge(
                    category=s.get('category'),
                    pattern=s.get('pattern'),
                    insight=s.get('insight'),
                    source_video_id=video_id,
                    script_style=s.get('script_style', script_style)
                )
            print(f"[Learning] Successfully learned {len(strategies)} strategies from {video_id}")
        else:
            print(f"[Learning] No strategies extracted from {video_id}")
    except Exception as e:
        import traceback
        print(f"[Learning] Failed to learn from {video_id}: {e}")
        traceback.print_exc()

# ===========================================
# 페이지 라우트
# ===========================================

@app.get("/", response_class=HTMLResponse)
async def page_home(request: Request):
    """메인 페이지 - 주제 찾기"""
    return templates.TemplateResponse("pages/topic.html", {
        "request": request,
        "page": "topic",
        "title": "주제 찾기"
    })

@app.get("/projects", response_class=HTMLResponse)
async def page_projects(request: Request):
    """내 프로젝트 페이지"""
    return templates.TemplateResponse("pages/projects.html", {
        "request": request,
        "page": "projects",
        "title": "내 프로젝트"
    })

@app.get("/script-plan", response_class=HTMLResponse)
async def page_script_plan(request: Request):
    """대본 기획 페이지"""
    return templates.TemplateResponse("pages/script_plan.html", {
        "request": request,
        "page": "script-plan",
        "title": "대본 기획"
    })

@app.get("/script-gen", response_class=HTMLResponse)
async def page_script_gen(request: Request):
    """대본 생성 페이지"""
    return templates.TemplateResponse("pages/script_gen.html", {
        "request": request,
        "page": "script-gen",
        "title": "대본 생성"
    })

@app.get("/image-gen", response_class=HTMLResponse)
async def page_image_gen(request: Request):
    """이미지 생성 페이지"""
    return templates.TemplateResponse("pages/image_gen.html", {
        "request": request,
        "page": "image-gen",
        "title": "이미지 생성"
    })

@app.get("/audio-gen", response_class=HTMLResponse)
async def page_audio_gen(request: Request):
    """오디오 생성 페이지"""
    return templates.TemplateResponse("pages/audio_gen.html", {
        "request": request,
        "page": "audio-gen",
        "title": "오디오 생성"
    })

@app.get("/video-gen", response_class=HTMLResponse)
async def page_video_gen(request: Request):
    """동영상 생성 페이지"""
    return templates.TemplateResponse("pages/video_gen.html", {
        "request": request,
        "page": "video-gen",
        "title": "동영상 생성"
    })

@app.get("/tts", response_class=HTMLResponse)
async def page_tts(request: Request):
    """TTS 생성 페이지"""
    return templates.TemplateResponse("pages/tts.html", {
        "request": request,
        "page": "tts",
        "title": "TTS 생성"
    })

@app.get("/render", response_class=HTMLResponse)
async def page_render(request: Request):
    """영상 렌더링 페이지"""
    return templates.TemplateResponse("pages/render.html", {
        "request": request,
        "page": "render",
        "title": "영상 렌더링"
    })

@app.get("/video-upload", response_class=HTMLResponse)
async def page_video_upload(request: Request):
    """영상 업로드 페이지"""
    return templates.TemplateResponse("pages/video_upload.html", {
        "request": request,
        "page": "video-upload",
        "title": "영상 업로드",
        "is_independent": auth_service.is_independent()
    })

@app.get("/subtitle_gen", response_class=HTMLResponse)
async def page_subtitle_gen(request: Request, project_id: int = Query(None)):
    """자막 생성/편집 페이지"""
    project = None
    if project_id:
        project = db.get_project(project_id)
    else:
        # Fallback: Load most recent project
        recent = db.get_recent_projects(limit=1)
        if recent:
            project = recent[0]
        
    return templates.TemplateResponse("pages/subtitle_gen.html", {
        "request": request,
        "page": "subtitle-gen",
        "title": "자막 편집",
        "project": project
    })


@app.get("/title-desc", response_class=HTMLResponse)
async def page_title_desc(request: Request):
    """제목/설명 생성 페이지"""
    return templates.TemplateResponse("pages/title_desc.html", {
        "request": request,
        "page": "title-desc",
        "title": "제목/설명 생성"
    })

@app.get("/thumbnail", response_class=HTMLResponse)
async def page_thumbnail(request: Request):
    """썸네일 생성 페이지"""
    return templates.TemplateResponse("pages/thumbnail.html", {
        "request": request,
        "page": "thumbnail",
        "title": "썸네일 생성"
    })

@app.get("/shorts", response_class=HTMLResponse)
async def page_shorts(request: Request):
    """쇼츠 생성 페이지"""
    return templates.TemplateResponse("pages/shorts.html", {
        "request": request,
        "page": "shorts",
        "title": "쇼츠 생성"
    })

@app.get("/commerce-shorts", response_class=HTMLResponse)
async def page_commerce_shorts(request: Request):
    """커머스 쇼츠 페이지"""
    return templates.TemplateResponse("pages/commerce_shorts.html", {
        "request": request,
        "page": "commerce-shorts",
        "title": "커머스 쇼츠"
    })

@app.get("/settings", response_class=HTMLResponse)
async def page_settings(request: Request):
    """설정 페이지"""
    return templates.TemplateResponse("pages/settings.html", {
        "request": request,
        "page": "settings",
        "title": "설정"
    })


# ===========================================
# API: 프로젝트 관리 (모듈화 완료 - 상단에서 include됨)
# ===========================================

@app.post("/api/script/recommend-titles")
async def recommend_titles(
    keyword: str = Body(..., embed=True),
    topic: str = Body("", embed=True),
    language: str = Body("ko", embed=True)
):
    """키워드 기반 제목 추천"""
    titles = await gemini_service.generate_title_recommendations(keyword, topic, language)
    return {"titles": titles}




@app.patch("/api/projects/{project_id}")
async def patch_project(project_id: int, body: dict = Body(...)):
    """프로젝트 기본 정보 업데이트 (이름, 주제 등)"""
    try:
        allowed = {k: v for k, v in body.items() if k in ('name', 'topic', 'status')}
        if allowed:
            db.update_project(project_id, **allowed)
        return {"status": "ok"}
    except Exception as e:
        raise HTTPException(500, str(e))


@app.post("/api/projects/{project_id}/script")
async def save_script(project_id: int, req: ScriptSave):
    """대본 저장"""
    db.save_script(project_id, req.full_script, req.word_count, req.estimated_duration)
    db.update_project(project_id, status="scripted")
    return {"status": "ok"}

@app.get("/api/projects/{project_id}/script")
async def get_script(project_id: int):
    """대본 조회"""
    return db.get_script(project_id) or {}

@app.get("/api/projects/{project_id}/full")
async def get_project_full(project_id: int):
    """프로젝트 전체 데이터 조회 (Context Restoration용)"""
    return db.get_project_full_data_v2(project_id) or {}


@app.post("/api/projects/{project_id}/analyze-scenes")
async def analyze_scenes(project_id: int):
    """AI를 사용하여 대본을 분석하고 적절한 Scene 개수 결정"""
    # Get script
    script_data = db.get_script(project_id)
    script = ""
    
    if script_data and script_data.get("full_script"):
        script = script_data["full_script"]
    else:
        # Fallback to shorts
        shorts_data = db.get_shorts(project_id)
        if shorts_data and shorts_data.get("shorts_data"):
            try:
                scenes = shorts_data.get("shorts_data", {}).get("scenes", [])
                if not scenes and isinstance(shorts_data.get("shorts_data"), list):
                    scenes = shorts_data.get("shorts_data")
                
                script_parts = []
                for scene in scenes:
                    if isinstance(scene, dict):
                        text = scene.get("narration") or scene.get("dialogue") or scene.get("text", "")
                        if text:
                            script_parts.append(text)
                
                script = " ".join(script_parts)
            except Exception as e:
                print(f"Error extracting shorts script: {e}")
    
    if not script:
        raise HTTPException(400, "대본을 찾을 수 없습니다")
    
    # Analyze with Gemini
    try:
        analysis_prompt = f"""다음 대본을 분석하여 이미지 생성을 위한 적절한 Scene 개수를 결정해주세요.

대본:
{script}

지침:
- 대본의 내용 흐름을 고려하여 자연스럽게 나눌 수 있는 Scene 개수를 결정하세요
- 너무 적으면 (1-2개) 시각적 다양성이 부족하고, 너무 많으면 (50개 이상) 중복이 많아집니다
- 일반적으로 5-20개 사이가 적절합니다
- 대본 길이, 주제 전환, 내용 변화를 고려하세요

응답 형식 (JSON만 출력):
{{"scene_count": 숫자, "reason": "간단한 이유"}}"""

        response_text = await gemini_service.generate_text(analysis_prompt, temperature=0.3)
        
        # Extract JSON from response
        import json
        import re
        
        # Try to find JSON in response
        json_match = re.search(r'\{.*?\}', response_text, re.DOTALL)
        if json_match:
            result = json.loads(json_match.group())
            scene_count = result.get("scene_count")
            reason = result.get("reason", "")
            
            if scene_count and isinstance(scene_count, int) and 1 <= scene_count <= 100:
                return {"scene_count": scene_count, "reason": reason}
        
        # Fallback: try to extract number
        numbers = re.findall(r'\b(\d+)\b', response_text)
        if numbers:
            scene_count = int(numbers[0])
            if 1 <= scene_count <= 100:
                return {"scene_count": scene_count, "reason": "AI 자동 분석"}
        
        # Default fallback
        return {"scene_count": 10, "reason": "기본값"}
        
    except Exception as e:
        print(f"Scene analysis error: {e}")
        raise HTTPException(500, f"분석 실패: {str(e)}")


@app.post("/api/image/generate-prompts")
async def generate_image_prompts_api(req: PromptsGenerateRequest):
    """대본 기반 이미지 프롬프트 생성 (Unified API)"""
    try:
        # 1. Project Context & Duration Estimation
        duration = 60
        style_key = req.style
        characters = []

        if req.project_id:
            # Get latest script info
            p_data = db.get_script(req.project_id)
            if p_data:
                duration = p_data.get('estimated_duration', 60)
            
            # Get project settings (to resolve style key if generic)
            settings = db.get_project_settings(req.project_id)
            if settings:
                if not style_key or style_key == 'realistic' or style_key == 'default':
                    style_key = settings.get('image_style', style_key)
            
            # Get existing characters for the project
            characters = db.get_project_characters(req.project_id)
        
        if not duration:
            duration = len(req.script) // 5 # very rough char count est

        # 2. Style Prompt Resolution (Key -> Description)
        db_presets = db.get_style_presets()
        style_data = db_presets.get(style_key.lower())

        if style_data and isinstance(style_data, dict):
            style_prompt = style_data.get('prompt_value', style_key)
            gemini_instruction = style_data.get('gemini_instruction') or None
        else:
            style_prompt = STYLE_PROMPTS.get(style_key.lower(), style_key)
            gemini_instruction = None

        # 3. Call Gemini via Unified Service
        target_count = req.count if req.count and req.count > 0 else None
        print(f"[Prompts] Generating for Project {req.project_id}, Style: {style_key}, Target scenes: {target_count or 'auto'}, has_gemini_instruction: {bool(gemini_instruction)}")

        # [SAFETY] Truncate script to prevent Token Limit Exceeded / Timeout
        # 30000자로 늘림 (긴 대본도 전체 대사 포함)
        safe_script = req.script[:30000] if len(req.script) > 30000 else req.script
        if len(req.script) > 30000:
            print(f"[Prompts] Script truncated: {len(req.script)} → 30000 chars")

        prompts_list = await gemini_service.generate_image_prompts_from_script(
            safe_script,
            duration,
            style_prompt=style_prompt,
            characters=characters,
            target_scene_count=target_count,
            style_key=style_key,
            gemini_instruction=gemini_instruction
        )

        if not prompts_list:
            # Retry once if empty
            print("[Prompts] Empty result, retrying...")
            prompts_list = await gemini_service.generate_image_prompts_from_script(
                safe_script,
                duration,
                style_prompt=style_prompt,
                characters=characters,
                target_scene_count=target_count,
                style_key=style_key,
                gemini_instruction=gemini_instruction
            )

        if not prompts_list:
             raise HTTPException(500, "프롬프트 생성 실패 (AI 응답 오류)")

        # 4. Post-processing for UI consistency
        for p in prompts_list:
            # Ensure mandatory fields
            s_text = p.get('scene_text') or p.get('scene') or p.get('narrative') or ''
            p['scene_text'] = s_text
            
            if not p.get('scene_title'):
                p['scene_title'] = s_text[:15] + "..." if len(s_text) > 15 else f"Scene {p.get('scene_number', '?')}"
            
            # Ensure script bits exist
            if not p.get('script_start'):
                p['script_start'] = " ".join(s_text.split()[:2]) if s_text else ""
            if not p.get('script_end'):
                p['script_end'] = " ".join(s_text.split()[-2:]) if s_text else ""

            # Default empty states for UI
            if 'image_url' not in p: p['image_url'] = ""
            if 'image_path' not in p: p['image_path'] = ""

        # 5. [CRITICAL] DB에 실시간 저장 (UI에서 '적용' 버튼 누르기 전 미리 백업)
        if req.project_id:
            try:
                db.save_image_prompts(req.project_id, prompts_list)
                print(f"[Main] Auto-saved {len(prompts_list)} image prompts for project {req.project_id}")
            except Exception as e:
                print(f"[DB] Auto-save image prompts failed: {e}")

        return {"prompts": prompts_list}
        
    except Exception as e:
        print(f"Scene analysis error: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(500, f"분석 실패: {str(e)}")


@app.post("/api/projects/{project_id}/image-prompts/auto")
async def auto_generate_images(project_id: int):
    """대본 기반 이미지 프롬프트 생성 및 일괄 이미지 생성 (Longform & Shorts)"""
    # 1. 대본 조회 (Longform 우선, 없으면 Shorts 확인)
    script_data = db.get_script(project_id)
    script = ""
    duration = 60

    if script_data and script_data.get("full_script"):
        script = script_data["full_script"]
        duration = script_data.get("estimated_duration", 60)
    else:
        # Longform 대본이 없으면 Shorts 대본 확인
        shorts_data = db.get_shorts(project_id)
        if shorts_data and shorts_data.get("shorts_data"):
             # Shorts 데이터에서 텍스트 추출 (Narrations/Dialogue concatenating)
             # shorts_data structure might be complex, assuming simple list of scenes or text
             # Based on previous knowledge, shorts_data is likely a JSON with scenes
             try:
                 scenes = shorts_data.get("shorts_data", {}).get("scenes", [])
                 if not scenes and isinstance(shorts_data.get("shorts_data"), list):
                     scenes = shorts_data.get("shorts_data") # Handle list format
                 
                 parts = []
                 for s in scenes:
                     if "narration" in s: parts.append(s["narration"])
                     if "dialogue" in s: parts.append(s["dialogue"])
                     if "script" in s: parts.append(s["script"])
                 
                 script = "\n".join(parts)
                 duration = 50 # Default shorts duration
             except:
                 script = str(shorts_data) # Fallback
    
    if not script:
        raise HTTPException(400, "대본이 없습니다. 먼저 대본(Longform 또는 Shorts)을 생성해주세요.")

    # 2. 프롬프트 생성 (Gemini)
    from services.gemini_service import gemini_service
    prompts = await gemini_service.generate_image_prompts_from_script(script, duration)
    
    if not prompts:
        raise HTTPException(500, "이미지 프롬프트 생성 실패")

    # 3. 이미지 일괄 생성 (Imagen 3) - 병렬 처리
    async def process_scene(p):
        try:
            images = await gemini_service.generate_image(
                prompt=p["prompt_en"],
                aspect_ratio="16:9",
                num_images=1
            )
            
            if images:
                output_dir, web_dir = get_project_output_dir(project_id)
                filename = f"p{project_id}_s{p['scene_number']}_{int(time.time())}.png"
                output_path = os.path.join(output_dir, filename)
                
                with open(output_path, "wb") as f:
                    f.write(images[0])
                
                p["image_url"] = f"{web_dir}/{filename}"
                return True
        except Exception as e:
            print(f"이미지 생성 실패 (Scene {p.get('scene_number')}): {e}")
            p["image_url"] = ""
        return False

    print(f"🎨 [Main] 이미지 병렬 생성 시작: {len(prompts)}개...")
    tasks = [process_scene(p) for p in prompts]
    await asyncio.gather(*tasks)

    # 4. DB 저장
    db.save_image_prompts(project_id, prompts)

    return {"status": "ok", "prompts": prompts}



@app.post("/api/projects/{project_id}/tts/upload")
async def save_external_tts(project_id: int, file: UploadFile = File(...)):
    """외부 TTS 오디오 파일 업로드 및 저장"""
    try:
        # 1. 출력 경로 확보
        output_dir, web_dir = get_project_output_dir(project_id)
        
        # 2. 파일명 생성 (tts_ext_timestamp.mp3)
        import time
        ext = os.path.splitext(file.filename)[1]
        if not ext: ext = ".mp3"
        filename = f"tts_ext_{project_id}_{int(time.time())}{ext}"
        file_path = os.path.join(output_dir, filename)
        web_url = f"{web_dir}/{filename}"
        
        # 3. 저장
        content = await file.read()
        with open(file_path, "wb") as f:
            f.write(content)
            
        # 4. DB 업데이트 (TTS 결과로 등록)
        # save_tts(project_id, voice_id, voice_name, audio_path, duration)
        db.save_tts(project_id, "external_upload", "External Upload", file_path, 0.0)
        
        return {"status": "ok", "url": web_url, "path": file_path}
    except Exception as e:
        print(f"Error saving external TTS: {e}")
        return JSONResponse(status_code=500, content={"error": str(e)})

@app.post("/api/projects/{project_id}/image-prompts")
async def save_image_prompts(project_id: int, req: ImagePromptsSave):
    """이미지 프롬프트 저장"""
    db.save_image_prompts(project_id, req.prompts)
    return {"status": "ok"}

@app.get("/api/projects/{project_id}/image-prompts")
async def get_image_prompts(project_id: int):
    """이미지 프롬프트 조회"""
    return {"status": "ok", "prompts": db.get_image_prompts(project_id)}

class AnimateRequest(BaseModel):
    scene_number: int
    prompt: str = "Cinematic slow motion, high quality"
    duration: float = 5.0
    method: str = "standard"

@app.post("/api/projects/{project_id}/scenes/animate")
async def animate_scene(project_id: int, req: AnimateRequest):
    """이미지를 비디오로 변환 (Replicate Wan → AKOOL v4 폴백)"""
    try:
        # 1. 이미지 조회
        scene_prompts = db.get_image_prompts(project_id)
        target_scene = next((p for p in scene_prompts if p['scene_number'] == req.scene_number), None)
        if not target_scene or not target_scene.get('image_url'):
            return JSONResponse(status_code=404, content={"error": "해당 장면의 이미지를 찾을 수 없습니다."})

        image_web_path = target_scene['image_url']
        if image_web_path.startswith("/output/"):
            image_abs_path = os.path.join(config.OUTPUT_DIR, image_web_path.replace("/output/", "").lstrip("/"))
        else:
            image_abs_path = os.path.join(config.BASE_DIR, image_web_path.lstrip("/"))

        if not os.path.exists(image_abs_path):
            return JSONResponse(status_code=404, content={"error": f"이미지 파일 없음: {image_abs_path}"})

        motion_prompt = f"{req.prompt}, {target_scene.get('prompt_en', '')}"
        video_bytes = None

        # 1순위: Replicate Wan
        try:
            print(f"[Animate] Trying Replicate Wan...")
            video_bytes = await replicate_service.generate_video_from_image(
                image_path=image_abs_path,
                prompt=motion_prompt[:1000],
                duration=req.duration,
                method=req.method
            )
            print(f"[Animate] Replicate OK")
        except Exception as e:
            print(f"[Animate] Replicate failed ({str(e)[:80]}) -> AKOOL fallback")

        # 2순위: AKOOL v4
        if not video_bytes:
            try:
                print(f"[Animate] Trying AKOOL v4...")
                video_bytes = await akool_service.generate_akool_video_v4(
                    local_image_path=image_abs_path,
                    prompt=motion_prompt[:500],
                    duration=req.duration if req.duration else 5
                )
                print(f"[Animate] AKOOL v4 OK")
            except Exception as e:
                print(f"[Animate] AKOOL v4 failed: {e}")

        if not video_bytes:
            return JSONResponse(status_code=500, content={"error": "Replicate 크레딧 부족 + AKOOL도 실패. AKOOL API 키 및 크레딧을 확인하세요."})

        # 저장
        output_dir, web_dir = get_project_output_dir(project_id)
        filename = f"motion_p{project_id}_s{req.scene_number}_{int(time.time())}.mp4"
        output_path = os.path.join(output_dir, filename)
        with open(output_path, "wb") as f:
            f.write(video_bytes)

        video_web_url = f"{web_dir}/{filename}"
        db.update_image_prompt_video_url(project_id, req.scene_number, video_web_url)
        return {"status": "success", "video_url": video_web_url}

    except Exception as e:
        print(f"Animate Error: {e}")
        return JSONResponse(status_code=500, content={"error": str(e)})

@app.post("/api/upload-video-to-project/{project_id}/{scene_number}")
async def upload_scene_video(project_id: int, scene_number: int, file: UploadFile = File(...)):
    """확장프로그램 혹은 수동 업로드를 통한 장면 비디오 저장"""
    try:
        print(f"DEBUG: upload_scene_video called with project_id={project_id}, scene_number={scene_number}")
        output_dir, web_dir = get_project_output_dir(project_id)
        
        ext = os.path.splitext(file.filename)[1]
        if not ext: ext = ".mp4"
        filename = f"flow_p{project_id}_s{scene_number}_{int(time.time())}{ext}"
        file_path = os.path.join(output_dir, filename)
        web_url = f"{web_dir}/{filename}"
        
        content = await file.read()
        with open(file_path, "wb") as f:
            f.write(content)
            
        # DB 업데이트
        db.update_image_prompt_video_url(project_id, scene_number, web_url)
        
        return {"status": "ok", "url": web_url, "path": file_path}
    except Exception as e:
        print(f"Error saving scene video: {e}")
        return JSONResponse(status_code=500, content={"error": str(e)})


@app.post("/api/projects/{project_id}/tts")
async def save_tts_info(project_id: int, voice_id: str, voice_name: str, audio_path: str, duration: float):
    """TTS 정보 저장"""
    db.save_tts(project_id, voice_id, voice_name, audio_path, duration)
    db.update_project(project_id, status="tts_done")
    return {"status": "ok"}

@app.get("/api/projects/{project_id}/tts")
async def get_tts_info(project_id: int):
    """TTS 정보 조회"""
    return db.get_tts(project_id) or {}

@app.post("/api/projects/{project_id}/metadata")
async def save_metadata(project_id: int, req: MetadataSave):
    """메타데이터 저장"""
    db.save_metadata(project_id, req.titles, req.description, req.tags, req.hashtags)
    return {"status": "ok"}

@app.get("/api/projects/{project_id}/metadata")
async def get_metadata(project_id: int):
    """메타데이터 조회"""
    return db.get_metadata(project_id) or {}

@app.post("/api/projects/{project_id}/thumbnails")
async def save_thumbnails(project_id: int, req: ThumbnailsSave):
    """썸네일 아이디어 및 설정 저장"""
    db.save_thumbnails(project_id, req.ideas, req.texts, req.full_settings)
    return {"status": "ok"}

@app.get("/api/projects/{project_id}/thumbnails")
async def get_thumbnails(project_id: int):
    """썸네일 아이디어 조회"""
    return db.get_thumbnails(project_id) or {}

# [REMOVED] Duplicate thumbnail save endpoint (Moved to line ~1630 with updated logic)

@app.post("/api/projects/{project_id}/intro/save")
async def save_intro_video(project_id: int, file: UploadFile = File(...)):
    """인트로(배경) 동영상 업로드 및 저장"""
    try:
        # 1. 출력 경로 확보
        output_dir, web_dir = get_project_output_dir(project_id)
        
        # 2. 파일명 생성 (intro_timestamp.mp4)
        import time
        ext = os.path.splitext(file.filename)[1]
        if not ext: ext = ".mp4"
        filename = f"intro_{project_id}_{int(time.time())}{ext}"
        file_path = os.path.join(output_dir, filename)
        web_url = f"{web_dir}/{filename}"
        
        # 3. 저장
        content = await file.read()
        with open(file_path, "wb") as f:
            f.write(content)
            
        # 4. DB 업데이트 (background_video_url 설정을 사용하여 인트로/배경으로 지정)
        # intro_video_path에도 저장하여 렌더링 시 앞쪽에 자동 삽입되도록 함
        db.update_project_setting(project_id, 'background_video_url', web_url)
        db.update_project_setting(project_id, 'intro_video_path', file_path)
        # video_path는 '생성된' 결과물일 수 있으므로 null로 리셋하여 업로드된 영상을 우선시하게 둠
        db.update_project_setting(project_id, 'video_path', None)
        
        return {"status": "ok", "url": web_url, "path": file_path}
    except Exception as e:
        print(f"Error saving intro video: {e}")
        return JSONResponse(status_code=500, content={"error": str(e)})

@app.post("/api/projects/{project_id}/shorts")
async def save_shorts(project_id: int, req: ShortsSave):
    """쇼츠 저장"""
    db.save_shorts(project_id, req.shorts_data)
    return {"status": "ok"}

# [REMOVED] Duplicate full endpoint


@app.get("/api/projects/{project_id}/shorts")
async def get_shorts(project_id: int):
    """쇼츠 조회"""
    return db.get_shorts(project_id) or {}

# 프로젝트 핵심 설정 (10가지 요소)
# List of keys to sync to Global/Default settings (Project 1)
SYNC_KEYS = ['visual_style', 'image_style', 'image_style_prompt', 'thumbnail_style', 
             'script_style', 'voice_provider', 'voice_id', 'voice_name', 'voice_language',
             'character_ref_text', 'character_ref_image_path', 'duration_seconds']

@app.post("/api/projects/{project_id}/settings")
async def save_project_settings(project_id: int, req: ProjectSettingsSave):
    """프로젝트 핵심 설정 저장"""
    try:
        settings = {k: v for k, v in req.dict().items() if v is not None}
        db.save_project_settings(project_id, settings)
        
        # [FIX] Sync to Global Settings (Project 1)
        if project_id != 1:
            global_updates = {k: v for k, v in settings.items() if k in SYNC_KEYS}
            if global_updates:
                db.save_project_settings(1, global_updates)
                print(f"🔄 Synced {len(global_updates)} settings to Global (Project 1)")

        return {"status": "ok", "message": "Settings saved"}
    except Exception as e:
        print(f"Settings Save Error: {e}")
        return {"status": "error", "error": str(e)}

@app.get("/api/projects/{project_id}/settings")
async def get_project_settings(project_id: int):
    """프로젝트 핵심 설정 조회"""
    return db.get_project_settings(project_id) or {}

@app.patch("/api/projects/{project_id}/settings/{key}")
async def update_project_setting(project_id: int, key: str, value: str):
    """단일 설정 업데이트"""
    # 숫자 변환
    if key in ['duration_seconds', 'is_uploaded', 'subtitle_bg_enabled', 'subtitle_stroke_enabled']:
        value = int(value)
    elif key in ['subtitle_font_size', 'subtitle_stroke_width', 'subtitle_line_spacing', 'subtitle_bg_opacity']:
        value = float(value)
        
    result = db.update_project_setting(project_id, key, value)
    
    # [FIX] Sync to Global Settings (Project 1)
    if project_id != 1 and key in SYNC_KEYS:
        db.update_project_setting(1, key, value)
        print(f"🔄 Synced '{key}' to Global (Project 1)")

    if not result:
        raise HTTPException(400, f"유효하지 않은 설정 키: {key}")
    return {"status": "ok"}

@app.get("/api/settings/subtitle/default")
async def get_subtitle_defaults():
    """자막 스타일 기본값 조회"""
    return db.get_subtitle_defaults()

@app.post("/api/settings/subtitle/default")
async def save_subtitle_defaults(req: SubtitleDefaultSave):
    """자막 스타일 기본값 저장"""
    db.save_global_setting("subtitle_default_style", req.dict())
    return {"status": "ok"}


# ===========================================
# API: 상태 확인
# ===========================================

@app.get("/api/health")
async def health_check():
    """서버 상태 확인"""
    return {
        "status": "ok",
        "version": "2.0.0",
        "apis": {
            "youtube": bool(config.YOUTUBE_API_KEY),
            "gemini": bool(config.GEMINI_API_KEY),
            "elevenlabs": bool(config.ELEVENLABS_API_KEY),
            "typecast": bool(config.TYPECAST_API_KEY)
        }
    }


# ===========================================
# API: API 키 관리
# ===========================================

class ApiKeySave(BaseModel):
    youtube: Optional[str] = None
    gemini: Optional[str] = None
    elevenlabs: Optional[str] = None
    typecast: Optional[str] = None
    replicate: Optional[str] = None
    topview: Optional[str] = None
    akool_id: Optional[str] = None
    akool_secret: Optional[str] = None

@app.get("/api/settings/api-keys")
async def get_api_keys():
    """API 키 상태 조회 (마스킹)"""
    return config.get_api_keys_status()

@app.post("/api/settings/api-keys")
async def save_api_keys(req: ApiKeySave):
    """API 키 저장"""
    updated = []
    
    mapping = {
        'youtube': 'YOUTUBE_API_KEY',
        'gemini': 'GEMINI_API_KEY',
        'elevenlabs': 'ELEVENLABS_API_KEY',
        'typecast': 'TYPECAST_API_KEY',
        'replicate': 'REPLICATE_API_TOKEN',
        'topview': 'TOPVIEW_API_KEY',
        'akool_id': 'AKOOL_CLIENT_ID',
        'akool_secret': 'AKOOL_CLIENT_SECRET'
    }

    req_dict = req.dict()
    print(f"📡 [API_KEY] Save request received. Fields present: {[k for k,v in req_dict.items() if v is not None]}")
    for field, config_key in mapping.items():
        val = req_dict.get(field)
        if val is not None and val.strip():
            print(f"🔑 [API_KEY] Updating {field} -> {config_key} (len: {len(val.strip())})")
            config.update_api_key(config_key, val.strip())
            updated.append(field)

    return {
        "status": "ok",
        "updated": updated,
        "message": f"{len(updated)}개의 API 키가 저장되었습니다"
    }


# ===========================================
# API: 글로벌 설정 관리
# ===========================================

@app.get("/api/settings")
async def get_global_settings():
    """글로벌 설정 조회"""
    from services.settings_service import settings_service
    
    # 1. Load JSON settings
    settings = settings_service.get_settings()
    
    # 2. Merge DB global settings (Project 1)
    try:
        db_settings = db.get_project_settings(1)
        if db_settings:
            settings.update(db_settings)
    except Exception as e:
        print(f"Failed to merge DB settings: {e}")
    
    # 3. Override app_mode from global_settings table (authoritative source)
    db_app_mode = db.get_global_setting("app_mode")
    if db_app_mode:
        settings["app_mode"] = db_app_mode
    
    # 4. Webtoon settings from global_settings table
    settings["webtoon_auto_split"] = db.get_global_setting("webtoon_auto_split", True)
    settings["webtoon_smart_pan"] = db.get_global_setting("webtoon_smart_pan", True)
    settings["webtoon_convert_zoom"] = db.get_global_setting("webtoon_convert_zoom", True)
    
    return settings

@app.post("/api/settings")
async def save_global_settings(data: Dict[str, Any] = Body(...)):
    """글로벌 설정 저장"""
    from services.settings_service import settings_service
    
    # 1. Track previous mode for change detection
    previous_mode = db.get_global_setting("app_mode", "longform")
    
    # 2. Save app_mode to global_settings DB table (authoritative source)
    new_mode = data.get("app_mode")
    if new_mode:
        db.save_global_setting("app_mode", new_mode)
    
    # 3. Save webtoon settings to global_settings DB table
    if "webtoon_auto_split" in data:
        db.save_global_setting("webtoon_auto_split", data["webtoon_auto_split"])
    if "webtoon_smart_pan" in data:
        db.save_global_setting("webtoon_smart_pan", data["webtoon_smart_pan"])
    if "webtoon_convert_zoom" in data:
        db.save_global_setting("webtoon_convert_zoom", data["webtoon_convert_zoom"])
    
    # 4. Save remaining settings to JSON file
    settings_service.save_settings(data)
    
    # 5. Detect mode change
    mode_changed = (new_mode is not None) and (previous_mode != new_mode)
    
    return {
        "status": "ok",
        "mode_changed": mode_changed,
        "previous_mode": previous_mode,
        "new_mode": new_mode
    }


# ===========================================
# API: YouTube
# ===========================================

@app.post("/api/youtube/search")
async def youtube_search(req: SearchRequest):
    """YouTube 검색"""
    params = {
        "part": "snippet",
        "q": req.query,
        "type": "video",
        "maxResults": req.max_results,
        "order": req.order,
        "key": config.YOUTUBE_API_KEY
    }

    if req.published_after:
        params["publishedAfter"] = req.published_after

    if req.video_duration:
        params["videoDuration"] = req.video_duration
        
    if req.relevance_language:
        params["relevanceLanguage"] = req.relevance_language

    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"{config.YOUTUBE_BASE_URL}/search",
            params=params
        )
        return response.json()

@app.post("/api/projects/{project_id}/youtube/auto-upload")
async def auto_upload_youtube(project_id: int):
    """유튜브 원클릭 자동 업로드 (영상 + 메타데이터 + 썸네일)"""
    from services.youtube_upload_service import youtube_upload_service

    # 1. 데이터 조회
    project = db.get_project(project_id)
    settings = db.get_project_settings(project_id)
    meta = db.get_metadata(project_id)

    if not project or not settings:
        raise HTTPException(404, "프로젝트 정보를 찾을 수 없습니다.")

    # 2. 파일 경로 및 메타데이터 준비
    video_web_path = settings.get('video_path')
    if not video_web_path:
        raise HTTPException(400, "렌더링된 영상 파일 정보가 없습니다.")

    # 웹 경로 (/output/folder/file.mp4) -> 절대 경로 변환
    video_rel_path = video_web_path.replace('/output/', '', 1)
    video_path = os.path.join(config.OUTPUT_DIR, video_rel_path)

    if not os.path.exists(video_path):
        print(f"DEBUG: Video file not found at {video_path}")
        raise HTTPException(400, f"영상 파일을 찾을 수 없습니다: {os.path.basename(video_path)}")

    # 메타데이터 (저장된 게 없으면 기본값 사용)
    title = project['name']
    description = ""
    tags = []

    if meta:
        titles = meta.get('titles', [])
        if titles:
            title = titles[0] # 첫 번째 추천 제목 사용
        description = meta.get('description', "")
        tags = meta.get('tags', [])

    # 3. 업로드 수행
    try:
        response = youtube_upload_service.upload_video(
            file_path=video_path,
            title=title,
            description=description,
            tags=tags,
            privacy_status="private" # 기본은 비공개 (사용자가 검토 후 공개 전환)
        )

        video_id = response.get('id')
        if not video_id:
            raise Exception("업로드 응답에 비디오 ID가 없습니다.")

        # 4. 썸네일 설정 (있는 경우)
        thumb_url = settings.get('thumbnail_url')
        if thumb_url:
            # 웹 경로 (/output/file.png) -> 절대 경로 변환
            thumb_rel_path = thumb_url.replace('/output/', '', 1)
            thumb_path = os.path.join(config.OUTPUT_DIR, thumb_rel_path)
            
            if os.path.exists(thumb_path):
                youtube_upload_service.set_thumbnail(video_id, thumb_path)

        # 5. 상태 업데이트 (비디오 ID 저장)
        db.update_project_setting(project_id, 'youtube_video_id', video_id)
        db.update_project_setting(project_id, 'is_uploaded', 1)
        db.update_project_setting(project_id, 'is_published', 0) # 아직 비공개 상태이므로 0

        return {
            "status": "ok",
            "video_id": video_id,
            "url": f"https://youtu.be/{video_id}"
        }

    except Exception as e:
        print(f"Auto Upload Error: {e}")
        raise HTTPException(500, f"업로드 중 오류 발생: {str(e)}")

@app.post("/api/projects/{project_id}/youtube/public")
async def publicize_youtube_video(project_id: int):
    """유튜브 영상을 '공개(public)' 상태로 전환"""
    from services.youtube_upload_service import youtube_upload_service
    
    settings = db.get_project_settings(project_id)
    if not settings or not settings.get('youtube_video_id'):
        raise HTTPException(400, "업로드된 영상의 ID를 찾을 수 없습니다. 먼저 업로드를 진행해 주세요.")
    
    video_id = settings['youtube_video_id']
    
    try:
        youtube_upload_service.update_video_privacy(video_id, "public")
        
        # 상태 업데이트
        db.update_project_setting(project_id, 'is_published', 1)
        
        return {"status": "ok", "message": "영상이 공개 상태로 전환되었습니다."}
    except Exception as e:
        print(f"Publicize Error: {e}")
        raise HTTPException(500, f"공개 전환 중 오류 발생: {str(e)}")


@app.get("/api/youtube/videos/{video_id}")
async def youtube_video_detail(video_id: str):
    """YouTube 영상 상세 정보"""
    params = {
        "part": "snippet,statistics,contentDetails",
        "id": video_id,
        "key": config.YOUTUBE_API_KEY
    }

    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"{config.YOUTUBE_BASE_URL}/videos",
            params=params
        )
        return response.json()


@app.get("/api/youtube/comments/{video_id}")
async def youtube_comments(video_id: str, max_results: int = 100):
    """YouTube 댓글 조회"""
    params = {
        "part": "snippet",
        "videoId": video_id,
        "maxResults": max_results,
        "order": "relevance",
        "key": config.YOUTUBE_API_KEY
    }

    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"{config.YOUTUBE_BASE_URL}/commentThreads",
            params=params
        )
        return response.json()


@app.get("/api/youtube/channel/{channel_id}")
async def youtube_channel(channel_id: str):
    """YouTube 채널 정보"""
    params = {
        "part": "snippet,statistics",
        "id": channel_id,
        "key": config.YOUTUBE_API_KEY
    }

    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"{config.YOUTUBE_BASE_URL}/channels",
            params=params
        )
        return response.json()

# [NEW] Batch Analysis Request Model
class BatchAnalysisRequest(BaseModel):
    folder_name: str
    videos: List[dict] # {id, title, channelTitle, viewCount...}

@app.post("/api/topic/analyze-batch")
async def analyze_batch_videos(req: BatchAnalysisRequest):
    """선택한 영상 일괄 분석 및 시트 생성"""
    if not req.folder_name or not req.videos:
        raise HTTPException(400, "폴더명과 영상 목록은 필수입니다.")

    # 1. 폴더 생성
    sanitized_folder = "".join([c for c in req.folder_name if c.isalnum() or c in (' ', '-', '_')]).strip()
    target_dir = os.path.join(config.OUTPUT_DIR, "analysis", sanitized_folder)
    os.makedirs(target_dir, exist_ok=True)
    
    print(f"Batch Analysis Started: {len(req.videos)} videos -> {target_dir}")

    results = []
    
    # 2. 각 영상 분석 (병렬 처리 권장되지만, Rate Limit 고려하여 순차 or 세마포어)
    # 일단 순차 처리로 안정성 확보 (Gemini Rate Limit)
    from services.gemini_service import gemini_service
    
    for idx, vid in enumerate(req.videos):
        print(f"Analyzing {idx+1}/{len(req.videos)}: {vid.get('title')}")
        
        # 분석 요청
        analysis = await gemini_service.analyze_success_and_creation(vid)
        
        # 결과 정리
        row = {
            "No": idx + 1,
            "Video ID": vid.get('id'),
            "Original Title": vid.get('title'),
            "Channel": vid.get('channelTitle'),
            "Views": vid.get('viewCount'),
            "Success Factor": analysis.get('success_factor', '분석 실패'),
            "Benchmarked Title": analysis.get('benchmarked_title', ''),
            "Synopsis": analysis.get('synopsis', ''),
            "Upload Date": vid.get('publishedAt', '')[:10]
        }
        results.append(row)

    # 3. CSV/Excel 저장
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    
    # Try using Pandas for Excel if available
    file_url = ""
    try:
        import pandas as pd
        df = pd.DataFrame(results)
        filename = f"analysis_result_{timestamp}.xlsx"
        filepath = os.path.join(target_dir, filename)
        df.to_excel(filepath, index=False)
        print(f"Saved Excel: {filepath}")
        
        # 웹 접근 경로 (static serving 설정 필요, 현재 output_dir가 static인지 확인)
        # config.OUTPUT_DIR usually maps to /output/
        file_url = f"/output/analysis/{sanitized_folder}/{filename}"
        
    except ImportError:
        # Fallback to CSV
        import csv
        filename = f"analysis_result_{timestamp}.csv"
        filepath = os.path.join(target_dir, filename)
        
        keys = results[0].keys() if results else []
        with open(filepath, 'w', newline='', encoding='utf-8-sig') as f:
            if keys:
                writer = csv.DictWriter(f, fieldnames=keys)
                writer.writeheader()
                writer.writerows(results)
        
        print(f"Saved CSV (Pandas not found): {filepath}")
        file_url = f"/output/analysis/{sanitized_folder}/{filename}"

    return {
        "status": "ok",
        "file_url": file_url,
        "count": len(results),
        "folder_path": target_dir
    }




# ===========================================
# API: Gemini
# ===========================================

class StructureGenerateRequest(BaseModel):
    project_id: Optional[int] = None
    topic: str
    duration: int = 60
    tone: str = "informative"
    notes: Optional[str] = None
    target_language: Optional[str] = "ko"
    script_style: Optional[str] = "story" # 기본값: 옛날 이야기
    mode: str = "monologue" # monologue or dialogue

@app.post("/api/gemini/generate-structure")
async def generate_script_structure_api(req: StructureGenerateRequest):
    """대본 구조 생성 (중복 방지 적용)"""
    try:
        # 1. 최근 프로젝트 조회
        recent_projects = db.get_recent_projects(limit=5)
        recent_titles = [p['name'] for p in recent_projects]

        # [NEW] 스타일 프롬프트 가져오기
        from services.settings_service import settings_service
        all_settings = settings_service.get_settings()
        style_prompts = all_settings.get("script_styles", {})
        style_prompt = style_prompts.get(req.script_style, "")
        
        # [FIX] Fallback: Use style name as instruction if no custom prompt
        if not style_prompt and req.script_style:
            # Convert style key to readable instruction
            # e.g., "senior_story" -> "Write in a Senior Story style"
            style_label = req.script_style.replace('_', ' ').title()
            style_prompt = f"Write the script in '{style_label}' style. Adapt tone, pacing, and narrative structure to match this genre/format."

        # [NEW] 분석 데이터 구성 (영상 내용이 아닌 형식/스타일 학습용)
        # 프로젝트 ID가 있으면 DB에서 기존 분석 결과를 가져옴
        db_analysis = None
        if req.project_id:
            db_analysis = db.get_analysis(req.project_id)

        # Gemini가 숫자를 시간으로 인식하도록 단위 추가
        duration_str = f"{req.duration}초"

        analysis_data = {
            "topic": req.topic,
            "duration_category": duration_str,
            "tone": req.tone,
            "user_notes": req.notes,
            "script_style": req.script_style,
            "success_analysis": db_analysis.get("analysis_result") if db_analysis else None
        }

        # [NEW] 누적 지식 (Knowledge) 가져오기
        accumulated_knowledge = db.get_recent_knowledge(limit=10, script_style=req.script_style)

        # 3. Gemini 호출
        result = await gemini_service.generate_script_structure(
            analysis_data, 
            recent_titles, 
            target_language=req.target_language,
            style_prompt=style_prompt,
            accumulated_knowledge=accumulated_knowledge
        )
        
        if "error" in result:
            return {"status": "error", "error": result["error"]}
            
        return {"status": "ok", "structure": result}

    except Exception as e:
        import traceback
        error_msg = f"Server Error: {str(e)}\n{traceback.format_exc()}"
        print(error_msg)
        return {"status": "error", "error": f"서버 내부 오류: {str(e)}"}

@app.post("/api/gemini/deep-dive")
async def generate_deep_dive_script_api(req: StructureGenerateRequest):
    """여러 소스를 학습하여 고품질 '딥다이브' 대본 생성"""
    if not req.project_id:
        return {"status": "error", "error": "project_id is required for deep-dive"}
    
    try:
        result = await gemini_service.generate_deep_dive_script(
            project_id=req.project_id,
            topic=req.topic,
            duration_seconds=req.duration,
            target_language=req.target_language or "ko",
            user_notes=req.notes or "없음",
            mode=req.mode
        )
        
        if "error" in result:
            return {"status": "error", "error": result["error"]}
            
        return {"status": "ok", "result": result}
        
    except Exception as e:
        print(f"[Deep Dive Error] {e}")
        return {"status": "error", "error": str(e)}

@app.post("/api/gemini/generate")
async def gemini_generate(req: GeminiRequest):
    """Gemini 텍스트 생성"""
    url = f"{config.GEMINI_URL}?key={config.GEMINI_API_KEY}"

    payload = {
        "contents": [{"parts": [{"text": req.prompt}]}],
        "generationConfig": {
            "temperature": req.temperature,
            "maxOutputTokens": req.max_tokens
        }
    }

    async with httpx.AsyncClient(timeout=60.0) as client:
        response = await client.post(url, json=payload)
        result = response.json()

        if "candidates" in result:
            text = result["candidates"][0]["content"]["parts"][0]["text"]
            return {"status": "ok", "text": text}
        else:
            return {"status": "error", "error": result}

@app.get("/api/projects/{project_id}/characters")
async def get_project_characters_api(project_id: int):
    """프로젝트 캐릭터 정보 조회"""
    chars = db.get_project_characters(project_id)
    return {"status": "ok", "characters": chars}

@app.post("/api/projects/{project_id}/characters")
async def save_project_characters_manual(project_id: int, characters: List[Dict] = Body(...)):
    """수동으로 편집/추가한 캐릭터 정보 저장"""
    try:
        db.save_project_characters(project_id, characters)
        return {"status": "ok", "message": f"{len(characters)}명의 캐릭터 정보가 저장되었습니다."}
    except Exception as e:
        raise HTTPException(500, f"캐릭터 저장 실패: {str(e)}")

@app.post("/api/image/upload-scene")
async def upload_scene_image_api(
    file: UploadFile = File(...),
    project_id: int = Form(...),
    scene_index: int = Form(...)
):
    """특정 Scene을 위한 이미지 직접 업로드"""
    try:
        # 1. 경로 설정
        output_dir, web_dir = get_project_output_dir(project_id)
        
        # 2. 파일 저장
        ext = os.path.splitext(file.filename)[1].lower()
        if not ext in ['.jpg', '.jpeg', '.png', '.webp', '.gif', '.mp4', '.mov', '.webm']:
            if not ext: ext = ".png"
            
        filename = f"scene_{scene_index}_upload_{int(time.time())}{ext}"
        filepath = os.path.join(output_dir, filename)
        
        with open(filepath, "wb") as f:
            content = await file.read()
            f.write(content)
            
        # 3. DB 업데이트 (영구 저장 보장)
        web_url = f"{web_dir}/{filename}"
        if ext in ['.mp4', '.mov', '.webm']:
            db.update_image_prompt_video_url(project_id, scene_index, web_url)
        else:
            db.update_image_prompt_url(project_id, scene_index, web_url)

        # 4. URL 반환
        return {
            "status": "ok",
            "url": web_url,
            "image_url": web_url if ext not in ['.mp4', '.mov', '.webm'] else None,
            "video_url": web_url if ext in ['.mp4', '.mov', '.webm'] else None,
            "path": filepath
        }
    except Exception as e:
        print(f"Scene Upload Error: {e}")
        return {"status": "error", "error": str(e)}

@app.get("/api/projects/{project_id}/script-structure")
async def get_project_script_structure(project_id: int):
    """대본 구조 조회"""
    data = db.get_script_structure(project_id)
    if not data:
        # 404가 아니라 빈 객체 반환 (프론트엔드 처리 용이성)
        return {}
    return data

@app.post("/api/projects/{project_id}/script-structure")
async def save_project_script_structure(project_id: int, req: ScriptStructureSave):
    """대본 구조 저장"""
    try:
        # Pydantic 모델을 dict로 변환
        structure_data = req.dict()
        db.save_script_structure(project_id, structure_data)
        return {"status": "ok"}
    except Exception as e:
        import traceback
        traceback.print_exc()
        return {"status": "error", "error": str(e)}


class AnalysisRequest(BaseModel):
    video_id: str
    title: str
    channel_title: str
    description: str = ""
    tags: List[str] = []
    view_count: int = 0
    like_count: int = 0
    comment_count: int = 0
    published_at: str = ""
    thumbnail_url: str = ""
    transcript: Optional[str] = None

@app.post("/api/gemini/analyze-comments")
async def gemini_analyze_comments(req: AnalysisRequest):
    """비디오 종합 분석 (댓글 + 자막)"""
    # 1. 댓글 가져오기
    comments_data = await youtube_comments(req.video_id, 50) # 상위 50개만
    
    comments = []
    if "items" in comments_data:
        for item in comments_data["items"]:
            snippet = item["snippet"].get("topLevelComment", {}).get("snippet", {})
            text = snippet.get("textDisplay", "")
            if text:
                comments.append(text)

    # 2. Gemini Service를 통해 분석 수행
    try:
        from services.gemini_service import gemini_service
        analysis = await gemini_service.analyze_comments(
            comments=comments, 
            video_title=req.title, 
            transcript=req.transcript
        )
        
        # 분석 결과에 sentiment가 없거나 에러가 있는 경우 처리
        if "error" in analysis:
            return {"status": "error", "error": analysis["error"]}
            
        return {"status": "ok", "analysis": analysis, "comment_count": len(comments)}
        
    except Exception as e:
        print(f"분석 실패: {e}")
        return {"status": "error", "error": str(e)}


# ===========================================
# API: TTS
# ===========================================

@app.post("/api/tts/generate")
async def tts_generate(req: TTSRequest):
    """TTS 음성 생성"""
    import time
    from services.tts_service import tts_service

    now_kst = config.get_kst_time()
    
    # Provider별 확장자 설정
    # [FIX] Gemini는 현재 EdgeTTS(mp3)로 fallback되므로 mp3 사용
    ext = "mp3" # "wav" if req.provider == "gemini" else "mp3"
    filename = f"tts_{now_kst.strftime('%Y%m%d_%H%M%S')}.{ext}"

    output_path = None # 초기화
    
    # 프로젝트 ID가 있으면 전용 폴더 사용
    if req.project_id:
        output_dir, web_dir = get_project_output_dir(req.project_id)
        # 서비스(tts_service)가 output_dir를 동적으로 받아야 함.
        # 하지만 tts_service는 init에서 output_dir를 고정함.
        # 파일명에 절대 경로를 넘겨주면 os.path.join에서 무시되는 특성을 이용하거나,
        # 서비스를 수정해야 함. 
        # tts_service의 메서드들이 filename만 받고 내부에서 join함.
        # -> tts_service 메서드 호출 시 filename 인자에 '절대 경로'를 넘기면
        # os.path.join(base, absolute) -> absolute가 됨 (Windows/Linux 공통)
        # 테스트 필요하지만 Python os.path.join 스펙상 두번째 인자가 절대경로면 앞부분 무시됨.
        # 따라서 filename에 full path를 넘기면 됨.
        result_filename = os.path.normpath(os.path.abspath(os.path.join(output_dir, filename)))
    else:
        # Fallback
        web_dir = "/output"
        result_filename = os.path.normpath(os.path.abspath(os.path.join(config.OUTPUT_DIR, filename)))

        # ----------------------------------------------------------------
    try:
        # ----------------------------------------------------------------
        # 멀티 보이스 모드 처리
        # ----------------------------------------------------------------
        if req.multi_voice and req.voice_map:
            # 1. 텍스트 파싱 (Frontend와 동일한 로직: "이름: 대사")
            segments = []
            lines = req.text.split('\n')
            
            # 정규식: "이름: 대사" (마크다운 기호, 괄호, 공백 등에 유연하게 대응)
            # 1. 앞뒤 마크다운기호/괄호 허용: ^\s*[\*\_\[\(]*
            # 2. 화자 이름 캡처: ([^\s:\[\(\*\_]+)
            # 3. 뒤쪽 기호 및 지문(옵션): [\*\_\]\)]*[ \t]*(?:\([^)]*\))?[ \t]*
            # 4. 구분자 및 대사: [:：][ \t]*(.*)
            # (Note: .* allows empty content if the script has a speaker name followed by a newline)
            pattern = re.compile(r'^\s*[\*\_\[\(]*([^\s:\[\(\*\_]+)[\*\_\]\)]*[ \t]*(?:\([^)]*\))?[ \t]*[:：][ \t]*(.*)')
            
            current_chunk = []
            current_speaker = None
            
            # 파일명을 위한 타임스탬프
            base_filename = os.path.splitext(filename)[0]
            
            # 라인별 파싱 및 그룹화
            for line in lines:
                match = pattern.match(line.strip())
                if match:
                    # 새로운 화자 등장 -> 이전 청크 저장
                    if current_chunk:
                        segments.append({
                            "speaker": current_speaker,
                            "text": "\n".join(current_chunk)
                        })
                    current_speaker = match.group(1).strip()
                    # 백엔드에서도 화자 이름에서 특수기호 2차 정지
                    current_speaker = re.sub(r'[\*\_\#\[\]\(\)]', '', current_speaker).strip()
                    
                    content = match.group(2).strip()
                    current_chunk = [content]
                else:
                    # 화자 없음 -> 이전 화자에 이어서 추가 (없으면 default)
                    current_chunk.append(line.strip())
            
            # 마지막 청크 처리
            if current_chunk:
                segments.append({
                    "speaker": current_speaker,
                    "text": "\n".join(current_chunk)
                })

            # 2. 세그먼트별 오디오 생성 (동시 생성 개수 제한)
            import asyncio
            semaphore = asyncio.Semaphore(10) # 최대 10개 동시 요청
            
            async def process_segment(idx, segment):
                async with semaphore:
                    speaker = segment["speaker"]
                    seg_text = segment["text"]
                    
                    # 15,000자 대본의 경우 수백 개의 세그먼트가 나올 수 있으므로 로그 출력
                    if idx % 5 == 0 or idx == len(segments) - 1:
                        print(f"🎙️ [Main] TTS 세그먼트 생성 중... ({idx+1}/{len(segments)})")
                    
                    # 화자별 목소리 결정
                    target_voice = req.voice_map.get(speaker, req.voice_id)
                    
                    provider = req.provider
                    # [ROBUSTNESS] '기본 설정 따름' 등의 비어있는 값 처리
                    if not target_voice:
                        target_voice = req.voice_id
                    
                    seg_filename = f"{base_filename}_seg_{idx:03d}.mp3"
                    seg_path = os.path.join(output_dir, seg_filename)
                    
                    try:
                        if provider == "elevenlabs":
                             await tts_service.generate_elevenlabs(seg_text, target_voice, seg_path)
                        elif provider == "openai":
                             await tts_service.generate_openai(seg_text, target_voice, "tts-1", seg_path, req.speed)
                        else: # gemini / edge_tts
                             await tts_service.generate_gemini(seg_text, target_voice, req.language, req.style_prompt, seg_path, req.speed)
                        return seg_path
                    except Exception as e:
                        print(f"❌ Segment {idx} (Speaker: {speaker}) generation failed: {e}")
                        return None

            print(f"🎙️ [Main] 멀티보이스 TTS 병렬 생성 시작 (총 {len(segments)}개, 동시 10개 제한)...")
            print(f"DEBUG: Voice Map: {req.voice_map}")
            segment_tasks = [process_segment(i, s) for i, s in enumerate(segments)]
            audio_files = [f for f in await asyncio.gather(*segment_tasks) if f]
            
            # 3. 오디오 합치기
            if audio_files:
                print(f"🔄 [Main] 오디오 파일 병합 시작 ({len(audio_files)}개)...")
                output_path = None
                
                # Blocking IO/Processing을 ThreadPool에서 실행
                loop = asyncio.get_event_loop()
                
                def merge_audio_sync():
                    nonlocal output_path
                    # 1. Try Pydub (Faster, no re-encode usually)
                    try:
                        from pydub import AudioSegment
                        import imageio_ffmpeg
                        
                        # ffmpeg 경로 명시적 설정 (Windows WinError 2 방지)
                        ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
                        AudioSegment.converter = ffmpeg_exe
                        # AudioSegment.ffmpeg = ffmpeg_exe # 일부 버전 호환성
                        
                        # [Robustness] ffprobe check disabled or assumed optional for simple concat?
                        # Pydub uses info_json which requires ffprobe.
                        # If imageio_ffmpeg doesn't provide ffprobe, pydub fails on from_file.
                        # We can try to skip pydub if we suspect ffprobe is missing, 
                        # but let's try it and catch exception.
                        
                        combined = AudioSegment.empty()
                        for af in audio_files:
                            combined += AudioSegment.from_file(af)
                        
                        combined.export(result_filename, format="mp3")
                        output_path = result_filename
                        print(f"✅ [Main] pydub으로 오디오 병합 완료: {result_filename}")
                        return True
                    except Exception as pydub_err:
                        # WinError 2 often means ffprobe missing
                        print(f"⚠️ pydub 병합 실패 ({pydub_err}), MoviePy로 재시도합니다.")
                        return False

                # Run Pydub in thread
                pydub_success = await loop.run_in_executor(None, merge_audio_sync)
                
                if pydub_success:
                    pass # Done
                else:
                    # 2. Key Fallback: MoviePy (Re-encodes, slower but reliable with imageio)
                    def merge_moviepy_sync():
                        nonlocal output_path
                        try:
                            from moviepy import AudioFileClip, concatenate_audioclips
                        except ImportError:
                            from moviepy.audio.io.AudioFileClip import AudioFileClip
                            from moviepy.audio.AudioClip import concatenate_audioclips
                        
                        clips = []
                        try:
                            for af in audio_files:
                                try:
                                    clips.append(AudioFileClip(af))
                                except Exception as e:
                                    print(f"Failed to load clip {af}: {e}")
                            
                            if clips:
                                final_clip = concatenate_audioclips(clips)
                                final_clip.write_audiofile(result_filename, verbose=False, logger=None)
                                final_clip.close()
                                for clip in clips: clip.close()
                                output_path = result_filename
                                print(f"✅ [Main] MoviePy로 오디오 병합 완료: {result_filename}")
                                return True
                            else:
                                print(f"❌ [Main] MoviePy: No valid clips to merge.")
                                return False
                        except Exception as e:
                            print(f"❌ [Main] MoviePy 병합 실패: {e}")
                            return False
                            
                    moviepy_success = await loop.run_in_executor(None, merge_moviepy_sync)
                
                if output_path:
                    # 임시 파일 삭제
                    for af in audio_files:
                         try: os.remove(af)
                         except: pass
                else:
                    return {"status": "error", "error": "오디오 병합 실패 (Pydub 및 MoviePy 모두 실패)"}
            else:
                 return {"status": "error", "error": "생성된 오디오 세그먼트가 없습니다."}

        # ----------------------------------------------------------------
        # 일반(단일) 모드 처리
        # ----------------------------------------------------------------
        else:
            # 1. ElevenLabs
            if req.provider == "elevenlabs":
                result = await tts_service.generate_elevenlabs(
                    req.text, req.voice_id, result_filename
                )
                # ElevenLabs returns a dict containing metadata
                if isinstance(result, dict):
                    output_path = result.get("audio_path")
                else:
                    output_path = result
            # 2. Google Cloud
            elif req.provider == "google_cloud":
                output_path = await tts_service.generate_google_cloud(
                    req.text, req.voice_id, req.language, result_filename, req.speed
                )
            # 3. Gemini
            elif req.provider == "gemini":
                output_path = await tts_service.generate_gemini(
                    req.text, req.voice_id, req.language, req.style_prompt, result_filename, req.speed
                )
            # 4. OpenAI
            elif req.provider == "openai":
                output_path = await tts_service.generate_openai(
                    req.text, req.voice_id, "tts-1", result_filename, req.speed
                )
            # 5. gTTS (Default)
            else:
                output_path = await tts_service.generate_gtts(
                    req.text, req.language, result_filename
                )

        # 공통: DB 저장 및 리턴 처리
        # DB 저장 (프로젝트와 연결)
        if req.project_id:
             try:
                 # [FIX] Calculate actual duration before saving
                 duration = 0.0
                 try:
                     # Check file existence first
                     if os.path.exists(output_path):
                         # Try pydub first (more accurate for VBR/altered speed)
                         try:
                             import pydub
                             audio_seg = pydub.AudioSegment.from_file(output_path)
                             duration = audio_seg.duration_seconds
                         except ImportError:
                             # Fallback to MoviePy
                             try:
                                 from moviepy import AudioFileClip
                                 with AudioFileClip(output_path) as ac:
                                     duration = ac.duration
                             except: pass
                         except Exception as e:
                             print(f"pydub check failed: {e}")
                             # Fallback to MoviePy
                             try:
                                 from moviepy import AudioFileClip
                                 with AudioFileClip(output_path) as ac:
                                     duration = ac.duration
                             except: pass
                 except Exception as e:
                     print(f"Failed to calculate audio duration: {e}")

                 # [FIX] Logic for voice_id/name: Single voice should use actual ID
                 final_voice_id = "multi-voice" if req.multi_voice else (req.voice_id or "default")
                 final_voice_name = "Multi Voice" if req.multi_voice else (req.voice_id or "default")

                 db.save_tts(
                     req.project_id,
                     final_voice_id,
                     final_voice_name,
                     output_path,
                     duration
                 )
                 
                 # [FIX] Save script text to project settings
                 if req.text:
                     db.update_project_setting(req.project_id, "script", req.text)
                     print(f"DEBUG: Saved TTS text to project settings (len={len(req.text)})")

             except Exception as db_e:
                 print(f"TTS DB 저장 실패: {db_e}")
                 # Don't swallow! Raise or return error so frontend knows.
                 raise db_e
        
        # URL 생성
        if req.project_id:
            final_url = f"{web_dir}/{filename}"
        else:
            final_url = f"/output/{filename}"

        return {
            "status": "ok",
            "file": filename,
            "url": final_url,
            "full_path": output_path
        }

    except Exception as e:
        return {"status": "error", "error": str(e)}


@app.post("/api/upload/template")
async def upload_template_api(file: UploadFile = File(...)):
    """템플릿 이미지 업로드 (9:16 오버레이)"""
    try:
        # public/templates 폴더
        template_dir = os.path.join(config.STATIC_DIR, "templates")
        os.makedirs(template_dir, exist_ok=True)
        
        # 안전한 파일명
        filename = f"template_{int(time.time())}.png"
        filepath = os.path.join(template_dir, filename)
        
        # 저장
        with open(filepath, "wb") as f:
            content = await file.read()
            f.write(content)
            
        # DB 업데이트 (Global Setting assumes project_id=1 for defaults or handle strictly)
        # For now, we save it as a 'default' setting with project_id=0 or just update recent project?
        # Re-reading user request: "9:16 Template Image... for SHORTS".
        # Usually settings page updates a GLOBAL default or current project.
        # Let's assume GLOBAL default for new projects, or update specific project if provided.
        # However, `settings.html` seems to load 'global-ish' settings.
        # Let's check `db.update_project_setting`.
        # Actually, `settings.html` usually loads default settings from a dummy project or specific config.
        # But wait, `get_settings_api` fetches from `db.get_project_settings(None)`?
        # Let's fallback to updating the most recent project OR a specific logic.
        # Since `settings.html` seems to be global context, let's assume project_id=1 for now as 'default slot'
        # OR better: The user wants this "Applied to video".
        # Let's save the URL and let the frontend/backend use it.
        
        web_url = f"/static/templates/{filename}"
        
        # [HACK] For this specific user request, we might need to apply this to the CURRENT project being edited.
        # But settings.html is global. Let's update project_id=1 (often Default) AND return URL.
        # Ideally, we should have a `global_settings` table.
        # Existing `project_settings` references `project_id`.
        # Let's use `db.update_project_setting(1, ...)` as a placeholder for "Default" if no project context.
        # BUT, to be safe and consistent with previous patterns:
        # Check if we can store it in a way available to new projects.
        # For now, update global default project (ID 1)
        db.update_project_setting(1, 'template_image_url', web_url)
        
        return {"status": "ok", "url": web_url}
    except Exception as e:
        print(f"Template Upload Error: {e}")
        return {"status": "error", "error": str(e)}

@app.delete("/api/settings/template")
async def delete_template_api():
    """템플릿 이미지 삭제"""
    try:
        db.update_project_setting(1, 'template_image_url', None)
        return {"status": "ok"}
    except Exception as e:
        return {"status": "error", "error": str(e)}

# [REMOVED] Duplicate API key routes (Consolidated at line 960)


@app.get("/api/health")
async def health_check():
    """서버 상태 및 API 연결 확인"""
    # Simple check based on key existence
    # In a real app, you might want to make a lightweight request to each service
    status = {
        "status": "ok",
        "apis": {
            "youtube": bool(config.YOUTUBE_API_KEY),
            "gemini": bool(config.GEMINI_API_KEY),
            "elevenlabs": bool(config.ELEVENLABS_API_KEY),
            "replicate": bool(config.REPLICATE_API_TOKEN)
        }
    }
    return status

@app.get("/api/settings")
async def get_settings_api():
    """전체 설정 로드 (기본 프로젝트 ID=1 기준)"""
    try:
        # Load API Keys
        # ...
        
        # Load DB Settings (Project 1 as default container)
        p_settings = db.get_project_settings(1) or {}
        
        script_styles = {
            "news": "뉴스 스타일 프롬프트...",
            "story": "옛날 이야기 스타일...",
            "senior_story": "시니어 사연 스타일..."
        }
        # In a real app, these prompts might be in a separate table or JSON column. 
        # Here we mock or retrieve if saved.
        
        return {
            "status": "ok",
            "gemini_tts": {
                "voice_name": p_settings.get("voice_name"),
                "language_code": p_settings.get("voice_language"),
                "style_prompt": p_settings.get("voice_style_prompt")
            },
            "voice_provider": p_settings.get("voice_provider"),
            "voice_id": p_settings.get("voice_id") or p_settings.get("voice_name"), # fallback
            "visual_style": p_settings.get("visual_style"),
            "image_style": p_settings.get("visual_style"), # alias
            "thumbnail_style": p_settings.get("thumbnail_style"),
            "script_style": p_settings.get("script_style"),
            "app_mode": p_settings.get("app_mode", "longform"),
            "template_image_url": p_settings.get("template_image_url")
        }
    except Exception as e:
        return {"status": "error", "error": str(e)}


@app.post("/api/settings")
async def save_settings_api(settings: dict):
    """전체 설정 저장 (기본 프로젝트 ID=1 기준)"""
    try:
        # Check and save allowed keys
        # We use update_project_setting for specific keys or save_project_settings for bulk
        # For simplicity and consistence with db.py logic, let's use save_project_settings
        # But we need to be careful not to overwrite other fields if we only get partial data
        # settings.html sends: app_mode, gemini_tts, script_styles
        
        # 1. Flatten structure for DB
        flat_settings = {}
        if "app_mode" in settings:
            flat_settings["app_mode"] = settings["app_mode"]
            
        if "gemini_tts" in settings:
            g = settings["gemini_tts"]
            flat_settings["voice_name"] = g.get("voice_name")
            flat_settings["voice_language"] = g.get("language_code")
            flat_settings["voice_style_prompt"] = g.get("style_prompt")
            
        if "script_styles" in settings:
            # These might be saved in Global Settings or Project Settings?
            # DB schema 'project_settings' doesn't have individual script style columns except maybe mapped ones?
            # Let's check schema. We added 'script_style' column but that's current style.
            # Storing prompts: The Code in `get_settings_api` had them hardcoded dict.
            # We should probably store them in `global_settings` table or `project_settings` JSON column?
            # For now, let's focus on APP_MODE which is critical.
            pass

        # Save to Project 1 (Default Container)
        db.save_project_settings(1, flat_settings)
        
        return {"status": "ok"}
    except Exception as e:
        print(f"Save Settings Error: {e}")
        return {"status": "error", "error": str(e)}


@app.patch("/api/projects/{project_id}/settings/{key}")
async def update_project_setting_api(project_id: int, key: str, value: Any = Query(...)):
    """단일 설정 업데이트 (Patch)"""
    try:
        db.update_project_setting(project_id, key, value)
        return {"status": "ok", "key": key, "value": value}
    except Exception as e:
        return {"status": "error", "error": str(e)}

@app.post("/api/projects/{project_id}/settings")
async def save_project_settings_api_bulk(project_id: int, settings: dict):
    """프로젝트 설정 일괄 저장 (자막 스타일 등)"""
    try:
        db.save_project_settings(project_id, settings)
        return {"status": "ok"}
    except Exception as e:
        import traceback
        traceback.print_exc()
        return {"status": "error", "error": str(e)}

@app.get("/api/tts/voices")
async def tts_voices():
    """사용 가능한 TTS 음성 목록"""
    voices = []

    # Gemini
    try:
        gemini_voices = tts_service.get_gemini_voices()
        for v in gemini_voices:
            voices.append({
                "id": v,
                "name": f"Gemini - {v}",
                "provider": "gemini"
            })
    except:
        pass

    # ElevenLabs
    if config.ELEVENLABS_API_KEY:
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    "https://api.elevenlabs.io/v1/voices",
                    headers={"xi-api-key": config.ELEVENLABS_API_KEY}
                )
                if response.status_code == 200:
                    data = response.json()
                    for v in data.get("voices", []):
                        voices.append({
                            "voice_id": v["voice_id"],
                            "name": v["name"],
                            "provider": "elevenlabs",
                            "preview_url": v.get("preview_url"),
                            "labels": v.get("labels", {})
                        })
        except:
            pass

    return {"voices": voices}


# ===========================================
# API: 자막 (Subtitle)
# ===========================================








# [NEW] Reset Timeline to Latest Generated State



# ===========================================
# API: 이미지 생성 (Gemini Imagen 3)
# ===========================================

class ImageGenerateRequest(BaseModel):
    prompt: str
    aspect_ratio: str = "9:16"  # 숏폼 전용 (9:16)


class ThumbnailTextRequest(BaseModel):
    """AI 썸네일 문구 생성 요청"""
    project_id: int
    thumbnail_style: str = "face"
    target_language: str = "ko"


class ThumbnailTextLayer(BaseModel):
    text: str
    position: str = "center" # top, center, bottom, custom
    y_offset: int = 0
    x_offset: int = 0
    font_family: str = "malgun"
    font_size: int = 72
    color: str = "#FFFFFF"
    stroke_color: Optional[str] = None
    stroke_width: int = 0
    bg_color: Optional[str] = None

class ThumbnailShapeLayer(BaseModel):
    x: int
    y: int
    width: int
    height: int
    color_start: str = "#000000"
    color_end: Optional[str] = None # 그라디언트 끝 색상 (없으면 단색)
    opacity: float = 1.0
    opacity_end: Optional[float] = None # 그라디언트 끝 투명도 (없으면 opacity와 동일)
    gradient_direction: str = "horizontal" # horizontal, vertical

class ThumbnailGenerateRequest(BaseModel):
    prompt: str
    shape_layers: List[ThumbnailShapeLayer] = []
    text_layers: List[ThumbnailTextLayer] = []
    # Legacy support
    text: Optional[str] = None
    text_position: str = "center"
    text_color: str = "#FFFFFF"
    font_size: int = 72
    language: str = "ko"
    background_path: Optional[str] = None # 기존 이미지 사용 시 경로

class ThumbnailBackgroundRequest(BaseModel):
    prompt: str
    aspect_ratio: Optional[str] = "16:9"  # [NEW] Aspect Ratio
    thumbnail_style: Optional[str] = None # [NEW] Layout/Composition Reference
    project_id: Optional[int] = None # [NEW] Project reference for Style Inheritance

class ThumbnailGenerateRequest(BaseModel):
    prompt: str
    layers: Optional[List[dict]] = None
    shape_layers: Optional[List[dict]] = None
    # Legacy support
    text: Optional[str] = None
    text_position: str = "center"
    text_color: str = "#FFFFFF"
    font_size: int = 72
    language: str = "ko"
    background_path: Optional[str] = None
    aspect_ratio: Optional[str] = "16:9"  # [NEW] Aspect Ratio


@app.post("/api/settings/thumbnail-style-sample/{style_key}")
async def upload_thumbnail_style_sample(style_key: str, file: UploadFile = File(...)):
    """썸네일 스타일 샘플 이미지 업로드"""
    try:
        # 디렉토리 생성
        save_dir = "static/thumbnail_samples"
        os.makedirs(save_dir, exist_ok=True)
        
        # 파일 저장 (확장자 유지 또는 png로 통일)
        # 여러 확장자 지원을 위해 파일명에 확장자 포함해서 저장 추천하지만,
        # 읽을 때 편의를 위해 png로 변환하거나 style_key.* 로 검색해야 함.
        # 편의상 저장된 파일명을 {style_key}.png 로 고정 (프론트에서 변환해주거나 여기서 변환)
        # 여기서는 원본 확장자를 사용하되, 읽을때 glob으로 찾는 방식 사용
        
        ext = file.filename.split('.')[-1] if '.' in file.filename else 'png'
        filename = f"{style_key}.{ext}" # 덮어쓰기
        filepath = os.path.join(save_dir, filename)
        
        # 기존 다른 확장자 파일 삭제 (중복 방지)
        for f in os.listdir(save_dir):
            if f.startswith(f"{style_key}."):
                try:
                    os.remove(os.path.join(save_dir, f))
                except: pass

        with open(filepath, "wb") as f:
            content = await file.read()
            f.write(content)
            
        return {"status": "ok", "url": f"/{save_dir}/{filename}"}
    except Exception as e:
        print(f"Sample Upload Error: {e}")
        return {"status": "error", "error": str(e)}

@app.post("/api/thumbnail/generate-text")
async def generate_thumbnail_text(req: ThumbnailTextRequest):
    """대본 기반 AI 썸네일 후킹 문구 자동 생성"""
    try:
        # 1. 프로젝트 데이터 가져오기
        project = db.get_project(req.project_id)
        if not project:
            return {"status": "error", "error": "프로젝트를 찾을 수 없습니다"}
        
        # 2. 대본 가져오기 (scripts 테이블 및 project_settings 동시 확인)
        script_data = db.get_script(req.project_id)
        script = script_data.get('full_script') if script_data else None
        
        if not script:
            return {"status": "error", "error": f"대본이 없습니다. 먼저 대본을 작성해주세요. (PID: {req.project_id})"}
        
        # 3. 프로젝트 설정에서 이미지 스타일 가져오기 (연동)
        settings = db.get_project_settings(req.project_id)
        image_style = settings.get('image_style', '') if settings else ''
        
        # 4. AI 프롬프트 생성
        from services.prompts import prompts
        
        # 대본이 너무 길면 앞부분만 사용 (토큰 절약)
        script_preview = script[:2000] if len(script) > 2000 else script
        
        # [NEW] Get character info for better context
        characters = db.get_project_characters(req.project_id)
        char_context = ""
        if characters:
            char_names = [c.get("name") for c in characters if c.get("name")]
            char_context = f"\n[Featured Characters]: {', '.join(char_names)}"

        prompt = prompts.GEMINI_THUMBNAIL_HOOK_TEXT.format(
            script=f"{script_preview}{char_context}",
            thumbnail_style=req.thumbnail_style,
            image_style=image_style or '(없음)',
            target_language=req.target_language
        )
        
        # 5. Gemini 호출
        
        # [NEW] Check for Style Sample Image
        sample_img_dir = "static/thumbnail_samples"
        sample_img_bytes = None
        
        if os.path.exists(sample_img_dir):
            for f in os.listdir(sample_img_dir):
                if f.startswith(f"{req.thumbnail_style}."):
                    try:
                        with open(os.path.join(sample_img_dir, f), "rb") as img_f:
                            sample_img_bytes = img_f.read()
                        break
                    except: pass
        
        if sample_img_bytes:
             print(f"[{req.thumbnail_style}] Using sample image for text generation")
             # Add context about image
             prompt += "\n\n[IMPORTANT] The attached image is a STYLE REFERENCE. Ensure the generated hook texts match the visual mood and intensity of this image."
             result = await gemini_service.generate_text_from_image(prompt, sample_img_bytes)
        else:
             result = await gemini_service.generate_text(prompt, temperature=0.8)
        
        # 6. JSON 파싱
        import json, re
        json_match = re.search(r'\{[\s\S]*\}', result)
        if json_match:
            data = json.loads(json_match.group())
            texts = data.get("texts", [])
            reasoning = data.get("reasoning", "")
            
            return {
                "status": "ok", 
                "texts": texts, 
                "reasoning": reasoning
            }
        
        # Enhanced Fallback: Use project title or "Must Watch"
        title = project.get("topic", "Must Watch")
        return {
            "status": "ok", 
            "texts": [title, f"🔥 {title}", f"✨ {title}"], 
            "reasoning": "Fallback used (AI JSON parsing failed)"
        }
        
    except Exception as e:
        print(f"[Thumbnail Text Gen Error] {e}")
        import traceback
        traceback.print_exc()
        return {"status": "error", "error": str(e)}

@app.post("/api/image/generate-thumbnail-background")
async def generate_thumbnail_background(req: ThumbnailBackgroundRequest):
    """썸네일 배경 이미지만 생성 (텍스트 없음)"""
    if not config.GEMINI_API_KEY:
        raise HTTPException(400, "Gemini API 키가 설정되지 않았습니다")

    try:
        from google import genai
        from PIL import Image
        import uuid

        client = genai.Client(api_key=config.GEMINI_API_KEY)

        # 1. Imagen 4로 배경 이미지 생성
        clean_prompt = req.prompt
        
        # [NEW] Style Inheritance architecture
        # 1. Art Style (from Project Settings)
        art_style_desc = ""
        if req.project_id:
            settings = db.get_project_settings(req.project_id)
            if settings:
                # Use image_style_prompt if available (this is the refined AI prompt)
                art_style_desc = settings.get('image_style_prompt') 
                if not art_style_desc and settings.get('image_style'):
                    # Fallback to fetching preset by key
                    presets = db.get_style_presets()
                    style_key = settings.get('image_style')
                    preset = presets.get(style_key)
                    if preset:
                        art_style_desc = preset.get('prompt_value')
        
        # 2. Layout/Composition Style (from Thumbnail Settings)
        layout_desc = ""
        if req.thumbnail_style:
            # 1. DB에서 스타일 설명 가져오기 (이제 레이아웃 중심)
            presets = db.get_thumbnail_style_presets() # Returns Dict[str, Dict]
            target_preset = presets.get(req.thumbnail_style)
            if target_preset:
                layout_desc = target_preset.get('prompt', '') # get_thumbnail_style_presets uses 'prompt' key
                print(f"[{req.thumbnail_style}] Using Layout preset description: {layout_desc}")
            
            # 2. 이미지 파일 분석 (있다면 추가/덮어쓰기)
            sample_img_dir = "static/thumbnail_samples"
            if os.path.exists(sample_img_dir):
                for f in os.listdir(sample_img_dir):
                    if f.startswith(req.thumbnail_style + '.'):
                        try:
                            with open(os.path.join(sample_img_dir, f), "rb") as img_f:
                                sample_img_bytes = img_f.read()
                            
                            print(f"[{req.thumbnail_style}] Analyzing sample image layout/style...")
                            analyze_prompt = "Describe the visual style, lighting, color palette, and composition of this image in 5 keywords for AI image generation. format: style1, style2, style3, ..."
                            vision_desc = await gemini_service.generate_text_from_image(analyze_prompt, sample_img_bytes)
                            layout_desc = f"{layout_desc}, {vision_desc}" if layout_desc else vision_desc
                            print(f"[{req.thumbnail_style}] Composition keywords from image: {vision_desc}")
                            break
                        except Exception as e:
                            print(f"Layout analysis failed: {e}")
                            pass
        
        final_style_components = []
        if art_style_desc:
            final_style_components.append(f"Visual Art Style: {art_style_desc}")
        if layout_desc:
            final_style_components.append(f"Composition & Layout: {layout_desc}")
        
        final_style_prefix = ". ".join(final_style_components) + ". " if final_style_components else ""

        # negative_constraints 강화
        negative_constraints = "text, words, letters, alphabet, typography, watermark, signature, speech bubble, logo, brand name, writing, caption, chinese characters, japanese kanji, korean hangul, hanzi"
        
        final_prompt = f"ABSOLUTELY NO TEXT. NO CHARACTERS. {final_style_prefix}{clean_prompt}. High quality, 8k, YouTube thumbnail background, empty background, no watermark. DO NOT INCLUDE: {negative_constraints}."

        # 이미지 생성 (전략: Replicate -> Gemini -> AKOOL Fallback)
        images_bytes = None
        
        # 1차 시도: Replicate (flux-schnell)
        try:
            print(f"🎨 [ThumbnailBG] Attempting Replicate (Primary)...")
            images_bytes = await replicate_service.generate_image(prompt=final_prompt, aspect_ratio=req.aspect_ratio)
        except Exception as e:
            print(f"⚠️ [ThumbnailBG] Replicate failed: {e}")

        # 2차 시도: Gemini Imagen (Fallback 1)
        if not images_bytes:
            try:
                print(f"🎨 [ThumbnailBG] Attempting Gemini Imagen (Fallback 1)...")
                images_bytes = await gemini_service.generate_image(
                    prompt=final_prompt,
                    num_images=1,
                    aspect_ratio=req.aspect_ratio
                )
            except Exception as e:
                print(f"⚠️ [ThumbnailBG] Gemini failed: {e}")

        # 3차 시도: AKOOL (Final Fallback)
        if not images_bytes:
            try:
                print(f"🎨 [ThumbnailBG] Attempting AKOOL (Final Fallback)...")
                images_bytes = await akool_service.generate_image(prompt=final_prompt, aspect_ratio=req.aspect_ratio)
            except Exception as e:
                print(f"⚠️ [ThumbnailBG] AKOOL failed: {e}")

        if not images_bytes:
            return {"status": "error", "error": "모든 이미지 생성 서비스가 실패했습니다."}
        
        # 2. 이미지 저장 (raw bytes → 파일)
        save_dir = "static/img/thumbnails"
        os.makedirs(save_dir, exist_ok=True)

        filename = f"bg_{uuid.uuid4().hex}.png"
        filepath = os.path.join(save_dir, filename)

        with open(filepath, 'wb') as f:
            f.write(images_bytes[0])
        
        # URL 및 절대 경로 반환
        return {
            "status": "ok",
            "url": f"/static/img/thumbnails/{filename}",
            "path": os.path.abspath(filepath)
        }

    except Exception as e:
        print(f"Error generating background: {e}")
        return {"status": "error", "error": str(e)}

@app.post("/api/projects/{project_id}/thumbnail/save")
async def save_project_thumbnail(project_id: int, file: UploadFile = File(...)):
    """최종 썸네일(합성본) 저장"""
    try:
        # 1. 저장 디렉토리 (output/thumbnails)
        # static 폴더 대신 output 폴더 사용 (확실한 서빙 보장)
        save_dir = os.path.join(config.OUTPUT_DIR, "thumbnails")
        os.makedirs(save_dir, exist_ok=True)
        
        # 2. 파일명 (project_{id}_{timestamp}.png)
        import time
        filename = f"thumbnail_{project_id}_{int(time.time())}.png"
        filepath = os.path.join(save_dir, filename)
        
        print(f"[Thumbnail] Saving to: {filepath}") # [DEBUG]
        
        # 3. 저장
        content = await file.read()
        if len(content) == 0:
            print("[Thumbnail] Error: Received empty file content")
            raise HTTPException(400, "Empty file received")

        with open(filepath, "wb") as f:
            f.write(content)
            
        print(f"[Thumbnail] Saved successfully. Size: {len(content)} bytes")

        # 4. URL 생성
        # output 폴더는 /output 으로 마운트되어 있음
        web_url = f"/output/thumbnails/{filename}"

        # 5. DB 업데이트 (thumbnail_path & thumbnail_url)
        try:
             db.update_project_setting(project_id, 'thumbnail_path', filepath)
             db.update_project_setting(project_id, 'thumbnail_url', web_url)
        except Exception as db_e:
             print(f"[Thumbnail] DB Update Failed: {db_e}")

        # 6. URL 반환
        return {
            "status": "ok",
            "url": web_url,
            "path": filepath
        }
    except Exception as e:
        print(f"Thumbnail save error: {e}")
        import traceback
        traceback.print_exc()
        return {"status": "error", "error": str(e)}

@app.post("/api/image/generate-thumbnail")
async def generate_thumbnail(req: ThumbnailGenerateRequest):
    """썸네일 생성 (이미지 + 텍스트 합성)"""
    if not config.GEMINI_API_KEY:
        raise HTTPException(400, "Gemini API 키가 설정되지 않았습니다")

    try:
        from google import genai
        from PIL import Image, ImageDraw, ImageFont
        import io
        import platform # Import platform for OS detection
        import re # Import regex

        # If background_path is provided, use it. Otherwise, generate new image.
        # If background_path is provided, use it. Otherwise, generate new image.
        img = None
        
        # [NEW] Dynamic Resolution
        target_size = (1280, 720) # Default 16:9
        if req.aspect_ratio == "9:16":
            target_size = (720, 1280)
        
        if req.background_path and os.path.exists(req.background_path):
            # 기존 이미지 로드
            try:
                img = Image.open(req.background_path)
                img = img.resize(target_size, Image.LANCZOS)
                print(f"Loaded background from: {req.background_path} (Resize: {target_size})")
            except Exception as e:
                pass

        if img is None: # If no bg or failed to load, generate
            from google import genai
            client = genai.Client(api_key=config.GEMINI_API_KEY)

            # 1. Imagen 4로 배경 이미지 생성 (무조건 텍스트 생성 억제)
            clean_prompt = req.prompt
            
            # negative_constraints 강화 (CJK 포함)
            negative_constraints = "text, words, letters, alphabet, typography, watermark, signature, speech bubble, logo, brand name, writing, caption, chinese characters, japanese kanji, korean hangul, hanzi"
            
            response = client.models.generate_images(
                model="imagen-4.0-generate-001",
                prompt=f"ABSOLUTELY NO TEXT. {clean_prompt}. Background only. High quality, 8k. DO NOT INCLUDE: {negative_constraints}.",
                config={
                    "number_of_images": 1,
                    "aspect_ratio": req.aspect_ratio, # [NEW]
                    "safety_filter_level": "BLOCK_LOW_AND_ABOVE"
                }
            )
            if response.generated_images:
                 img = response.generated_images[0].image._pil_image
                 img = img.resize(target_size, Image.LANCZOS)
            else:
                 raise HTTPException(500, "Background generation failed")
            
            # [FORCE FIX] 사용자 요청: 절대 텍스트 금지 (프롬프트 전처리)
            # [FORCE FIX] 사용자 요청: 절대 텍스트 금지 (프롬프트 전처리)
            # 2. negative_constraints 강화 (CJK 포함)
            negative_constraints = "text, words, letters, alphabet, typography, watermark, signature, speech bubble, logo, brand name, writing, caption, chinese characters, japanese kanji, korean hangul, hanzi"
            
            final_prompt = f"ABSOLUTELY NO TEXT. NO CHINESE/JAPANESE/KOREAN CHARACTERS. {clean_prompt}. High quality, 8k, detailed, YouTube thumbnail background, empty background, no watermark. DO NOT INCLUDE: {negative_constraints}. INVISIBLE TEXT."

            # 최신 google-genai SDK는 config에 negative_prompt 지원 가능성 높음 (또는 튜닝된 템플릿 사용)
            response = client.models.generate_images(
                model="imagen-4.0-generate-001",
                prompt=final_prompt,
                config={
                    "number_of_images": 1,
                    "aspect_ratio": "16:9",
                    "safety_filter_level": "BLOCK_LOW_AND_ABOVE"
                }
            )

            if not response.generated_images:
                return {"status": "error", "error": "배경 이미지 생성 실패"}

            # 2. 이미지 로드
            img_data = response.generated_images[0].image._pil_image
            img = img_data.resize((1280, 720), Image.LANCZOS)


        # 3. 텍스트 오버레이

        # 3. 도형 및 텍스트 오버레이

        # Helper: 그라디언트 사각형 그리기 (Alpha Interpolation 지원)
        def draw_gradient_rect(draw, img, x, y, w, h, start_color, end_color, direction="horizontal", start_opacity=1.0, end_opacity=None):
            if end_opacity is None:
                end_opacity = start_opacity

            # PIL Draw는 그라디언트 미지원 -> 이미지 합성으로 처리
            # 1. 그라디언트 마스크 생성
            base = Image.new('RGBA', (w, h), (0, 0, 0, 0))
            draw_base = ImageDraw.Draw(base)
            
            # 색상 파싱
            from PIL import ImageColor
            c1 = ImageColor.getrgb(start_color)
            c2 = ImageColor.getrgb(end_color) if end_color else c1
            
            # Alpha 값 (0-255 scaling)
            a1 = int(255 * start_opacity)
            a2 = int(255 * end_opacity)

            if not end_color or (start_color == end_color and start_opacity == end_opacity):
                # 단색 (색상도 같고 투명도도 같을 때)
                draw_base.rectangle([(0, 0), (w, h)], fill=c1 + (a1,))
            else:
                # 그라디언트 (색상 OR 투명도가 다를 때)
                for i in range(w if direction == 'horizontal' else h):
                    ratio = i / float((w if direction == 'horizontal' else h))
                    
                    # RGB Interpolation
                    r = int(c1[0] * (1 - ratio) + c2[0] * ratio)
                    g = int(c1[1] * (1 - ratio) + c2[1] * ratio)
                    b = int(c1[2] * (1 - ratio) + c2[2] * ratio)
                    
                    # Alpha Interpolation
                    a = int(a1 * (1 - ratio) + a2 * ratio)
                    
                    if direction == 'horizontal':
                        draw_base.line([(i, 0), (i, h)], fill=(r, g, b, a))
                    else:
                        draw_base.line([(0, i), (w, i)], fill=(r, g, b, a))
            
            # 원본 이미지에 합성
            img.paste(base, (x, y), base)

        # 3.1 도형 렌더링 (텍스트보다 뒤에)
        if hasattr(req, 'shape_layers') and req.shape_layers:
            draw = ImageDraw.Draw(img) # Draw 객체 생성 (단색은 직접 그리지만 그라디언트는 paste 사용)
            for shape in req.shape_layers:
                draw_gradient_rect(
                    draw, img, 
                    shape.x, shape.y, shape.width, shape.height,
                    shape.color_start, shape.color_end,
                    shape.gradient_direction, 
                    start_opacity=shape.opacity,
                    end_opacity=shape.opacity_end
                )

        # 3.2 텍스트 오버레이
        draw = ImageDraw.Draw(img)
        system = platform.system()

        # 레거시 요청을 새로운 형식으로 변환
        layers = req.text_layers
        if not layers and req.text:
            layers = [ThumbnailTextLayer(
                text=req.text,
                position=req.text_position,
                color=req.text_color,
                font_size=req.font_size
            )]

        for layer in layers:
            # 폰트 결정 (static/fonts 우선 탐색)
            font_candidates = []
            
            # [Smart Fix] 일본어/한자 포함 여부 확인 (Gmarket Sans는 한자 미지원)
            has_japanese = bool(re.search(r'[\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff]', layer.text))
            
            # 1. 프로젝트 내 폰트
            if layer.font_family == "gmarket":
                if has_japanese:
                    # Gmarket 요청이지만 일본어가 있으면 -> 윈도우용 굵은 일본어 폰트 파일명으로 대체
                    # Meiryo Bold, Malgun Gothic Bold, Yu Gothic Bold
                    font_candidates.extend(["meiryob.ttc", "malgunbd.ttf", "YuGothB.ttc", "msgothic.ttc"])
                    print(f"[Thumbnail] 'gmarket' requested but Japanese text detected. Fallback to System Bold font filenames.")
                else:
                    font_candidates.extend(["static/fonts/GmarketSansBold.woff", "static/fonts/GmarketSansBold.ttf", "GmarketSansBold.otf"])
            elif layer.font_family == "cookie":
                 # 쿠키런도 한자 지원이 제한적일 수 있음 -> 필요시 유사 로직 추가
                font_candidates.extend(["static/fonts/CookieRun-Regular.woff", "static/fonts/CookieRun-Regular.ttf", "CookieRun-Regular.ttf"])
            
            # 2. 시스템 폰트 Fallback
            if system == 'Windows':
                # Meiryo(일본어), Malgun(한국어) 순서
                font_candidates.extend(["meiryo.ttc", "meiryob.ttc", "malgunbd.ttf", "malgun.ttf", "gulim.ttc", "arial.ttf"])
            else:
                font_candidates.extend(["AppleGothic.ttf", "NotoSansCJK-Bold.ttc", "Arial.ttf"])

            font = None
            for font_file in font_candidates:
                # 1. 절대/상대 경로 직접 확인
                if os.path.exists(font_file):
                    try:
                        font = ImageFont.truetype(font_file, layer.font_size)
                        print(f"[Thumbnail] Loaded font: {font_file}")
                        break
                    except Exception as e:
                        print(f"[Thumbnail] Font load error ({font_file}): {e}")
                        continue
                
                # 2. Windows Fonts 폴더 확인
                if system == 'Windows':
                    win_path = os.path.join(os.environ.get('WINDIR', 'C:\\Windows'), 'Fonts', font_file)
                    if os.path.exists(win_path):
                        try:
                            font = ImageFont.truetype(win_path, layer.font_size)
                            break
                        except: continue

            if not font:
                font = ImageFont.load_default()

            # 텍스트 크기 계산 (Bbox)
            bbox = draw.textbbox((0, 0), layer.text, font=font)
            tw = bbox[2] - bbox[0]
            th = bbox[3] - bbox[1]

            # X 위치 (중앙 정렬 기반) + X 오프셋 적용
            x = (1280 - tw) // 2 + layer.x_offset
            
            # Y 위치 (720p 기준 5분할 강조) - [FIX] 하단 여백 확보
            if layer.position == "row1" or layer.position == "top":
                y = 60 + layer.y_offset
            elif layer.position == "row2":
                y = 190 + layer.y_offset
            elif layer.position == "row3":
                y = 320 + layer.y_offset
            elif layer.position == "row4":
                y = 450 + layer.y_offset
            elif layer.position == "row5" or layer.position == "bottom":
                y = 550 + layer.y_offset # [FIX] 580 -> 550 (바닥 붙음 방지)
            else: # center
                y = (720 - th) // 2 + layer.y_offset

            # 1. 배경 박스 (Highlights) - 텍스트 아래에 그려야 함
            if layer.bg_color:
                padding_x = 15
                padding_y = 10
                draw.rectangle(
                    [x - padding_x, y - padding_y, x + tw + padding_x, y + th + padding_y],
                    fill=layer.bg_color
                )

            # 2. 외곽선 (Strokes)
            if layer.stroke_color and layer.stroke_width > 0:
                for ox in range(-layer.stroke_width, layer.stroke_width + 1):
                    for oy in range(-layer.stroke_width, layer.stroke_width + 1):
                        draw.text((x + ox, y + oy), layer.text, font=font, fill=layer.stroke_color)

            # 3. 텍스트 그림자 (Stroke가 없을 때 가독성용)
            elif not layer.stroke_color:
                draw.text((x + 2, y + 2), layer.text, font=font, fill="#000000")

            # 4. 본문 텍스트 생성 (가장 위에 그려야 함)
            draw.text((x, y), layer.text, font=font, fill=layer.color)

        # 4. 저장
        now_kst = config.get_kst_time()
        filename = f"thumbnail_{now_kst.strftime('%Y%m%d_%H%M%S')}.png"
        
        output_dir = os.path.join(config.OUTPUT_DIR)
        os.makedirs(output_dir, exist_ok=True)
        
        output_path = os.path.join(output_dir, filename)
        img.save(output_path)

        web_url = f"/output/{filename}"
        return {"status": "ok", "url": web_url}

    except Exception as e:
        print(f"Error generating thumbnail: {e}")
        import traceback
        traceback.print_exc()
        return {"status": "error", "error": f"서버 오류: {str(e)}"}



@app.get("/api/trends/keywords")
async def get_trending_keywords(
    language: str = Query("ko", description="Target language code"),
    period: str = Query("now", description="Time period (now, week, month)"),
    age: str = Query("all", description="Target age group (all, 10s, 20s, 30s, 40s, 50s)")
):
    """국가/언어/기간/연령별 실시간 트렌드 키워드 조회"""
    if not config.GEMINI_API_KEY:
        raise HTTPException(500, "Gemini API key missing")
        
    keywords = await gemini_service.generate_trending_keywords(language, period, age)
    return {
        "status": "ok", 
        "language": language, 
        "period": period, 
        "age": age, 
        "keywords": keywords
    }






@app.post("/api/image/analyze-character")
async def analyze_character(
    file: Optional[UploadFile] = File(None),
    image_path: Optional[str] = Form(None),
    project_id: Optional[int] = Form(None) # [NEW] Persistence support
):
    try:
        image_bytes = None
        saved_image_url = None
        
        # 1. Check Uploaded File
        if file:
            image_bytes = await file.read()
            # [NEW] Save file for persistence if project_id provided
            if project_id and image_bytes:
                try:
                    save_dir = f"static/project_data/{project_id}"
                    os.makedirs(save_dir, exist_ok=True)
                    ext = file.filename.split('.')[-1] if '.' in file.filename else 'png'
                    filename = f"char_ref_{int(datetime.datetime.now().timestamp())}.{ext}"
                    filepath = os.path.join(save_dir, filename)
                    with open(filepath, "wb") as f:
                        f.write(image_bytes)
                    saved_image_url = f"/{save_dir.replace(os.sep, '/')}/{filename}"
                    print(f"Saved character ref to {saved_image_url}")
                except Exception as e:
                    print(f"Failed to save character ref image: {e}")
            
        # 2. Check Local Path (Thumbnail fallback)
        elif image_path:
            saved_image_url = image_path # Reuse provided path
            # Basic path validation
            if os.path.exists(image_path):
                with open(image_path, "rb") as f:
                    image_bytes = f.read()
            else:
                 # Check relative path from current dir
                 rel_path = image_path.lstrip("/").replace("/", os.sep)
                 if os.path.exists(rel_path):
                     with open(rel_path, "rb") as f:
                         image_bytes = f.read()
        
        if not image_bytes:
             return JSONResponse(status_code=400, content={"error": "Image file or valid path required"})

        # 3. Vision Analysis
        # 3. Vision Analysis
        prompt = """
        Analyze this image and provide a highly detailed, identity-focused description of the main character (or subject). 
        
        [CRITICAL REQUIREMENT]
        YOU MUST EXPLICITLY STATE THE RACE / ETHNICITY / NATIONALITY of the person (e.g., "Korean woman", "Japanese man", "Caucasian female"). 
        DO NOT leave this ambiguous. If they look East Asian, say "East Asian" or specific nationality if apparent.
        
        Capture specific facial features (eye shape, nose structure, jawline), exact hair texture/color/style, skin tone, and body proportions.
        Describe the clothing and accessories in detail.
        The goal is to generate a new image of the SAME person in a different setting, so the description must be specific enough to preserve identity.
        Output ONLY the description text. Start with "(Character Reference) A photo of...".
        """
        
        description = await gemini_service.generate_text_from_image(prompt, image_bytes)
        
        return {"description": description.strip(), "image_url": saved_image_url}
        
    except Exception as e:
        print(f"Analyze character failed: {e}")
        return JSONResponse(status_code=500, content={"error": str(e)})

class CharacterPromptRequest(BaseModel):
    script: str
    project_id: Optional[int] = None
    style: Optional[str] = "realistic"


@app.post("/api/image/character-prompts")
async def generate_character_prompts(req: CharacterPromptRequest):
    """대본 기반 캐릭터 프롬프트 생성"""
    try:
        # [Manual Mode] Always re-analyze when requested via API
        # (Skip logic removed to allow style-consistent re-extraction)


        # [NEW] 비주얼 스타일 결정 (프롬프트 반영)
        db_presets = db.get_style_presets()
        style_prefix = "photorealistic"
        
        if req.style:
            style_data = db_presets.get(req.style.lower())
            if isinstance(style_data, dict):
                style_prefix = style_data.get("prompt_value", req.style)
            else:
                style_prefix = STYLE_PROMPTS.get(req.style.lower(), req.style)
        elif req.project_id:
            # 프로젝트 설정에서 스타일 조회
            settings = db.get_project_settings(req.project_id)
            if settings and settings.get('image_style'):
                image_style_key = settings['image_style'].lower()
                style_data = db_presets.get(image_style_key)
                if isinstance(style_data, dict):
                    style_prefix = style_data.get("prompt_value", image_style_key)
                else:
                    style_prefix = STYLE_PROMPTS.get(image_style_key, image_style_key)

        print(f"👥 [Main] 캐릭터 분석 시작... (Style: {style_prefix})")
        characters = await gemini_service.generate_character_prompts_from_script(req.script, visual_style=style_prefix)

        
        # [NEW] DB 저장
        if req.project_id:
            try:
                db.save_project_characters(req.project_id, characters)
                print(f"[Main] Saved {len(characters)} characters to DB for project {req.project_id}")
            except Exception as db_err:
                print(f"[Main] Failed to save characters: {db_err}")
        
        return {"status": "ok", "characters": characters}
    except Exception as e:
        import traceback
        error_trace = traceback.format_exc()
        print(f"Character prompts generation failed: {e}\n{error_trace}")
        return {"status": "error", "error": f"{str(e)}", "trace": error_trace}


# duplicate endpoint removed
@app.post("/api/image/generate-character")
async def generate_character_image(
    prompt: str = Body(...),
    project_id: int = Body(...),
    style: str = Body("realistic"),
    name: Optional[str] = Body(None)
):
    """캐릭터 이미지를 생성하고 저장 (Character Reference용)"""
    try:
        # [NEW] DB 스타일 프리셋 조회
        db_presets = db.get_style_presets()
        style_data = db_presets.get(style.lower())
        if isinstance(style_data, dict):
            detailed_style = style_data.get("prompt_value", STYLE_PROMPTS.get(style.lower(), style))
        else:
            detailed_style = STYLE_PROMPTS.get(style.lower(), style)
        
        full_prompt = f"{prompt}, {detailed_style}"
        
        print(f"👤 [Char Generation] Style: {style}, Prompt: {prompt[:100]}...")

        # 이미지 생성 (전략: Replicate -> Gemini -> AKOOL Fallback)
        images_bytes = None
        
        # 1차 시도: Replicate (flux-schnell)
        try:
            print(f"🎨 [Char Generation] Attempting Replicate (Primary)...")
            images_bytes = await replicate_service.generate_image(prompt=full_prompt, aspect_ratio="1:1")
        except Exception as e:
            print(f"⚠️ [Char Generation] Replicate failed: {e}")

        # 2차 시도: Gemini Imagen (Fallback 1)
        if not images_bytes:
            try:
                print(f"🎨 [Char Generation] Attempting Gemini Imagen (Fallback 1)...")
                images_bytes = await gemini_service.generate_image(
                    prompt=full_prompt,
                    num_images=1,
                    aspect_ratio="1:1"
                )
            except Exception as e:
                print(f"⚠️ [Char Generation] Gemini failed: {e}")

        # 3차 시도: AKOOL (Final Fallback)
        if not images_bytes:
            try:
                print(f"🎨 [Char Generation] Attempting AKOOL (Final Fallback)...")
                images_bytes = await akool_service.generate_image(prompt=full_prompt, aspect_ratio="1:1")
            except Exception as e:
                print(f"⚠️ [Char Generation] AKOOL failed: {e}")

        if not images_bytes:
            return {"status": "error", "error": "모든 이미지 생성 서비스가 실패했습니다."}
        
        output_dir, web_dir = get_project_output_dir(project_id)
        filename = f"char_{project_id}_{int(datetime.datetime.now().timestamp())}.png"
        file_path = os.path.join(output_dir, filename)
        web_url = f"{web_dir}/{filename}"

        with open(file_path, "wb") as f:
            f.write(images_bytes[0])
            
        print(f"✅ [Char Generation] Saved to {web_url}")
        
        # [NEW] DB 업데이트
        if name:
            try:
                db.update_character_image(project_id, name, web_url)
                print(f"[DB] Updated character image for {name}")
            except Exception as dbe:
                print(f"[DB] Failed to update character image: {dbe}")
        
        return {"status": "ok", "url": web_url, "path": file_path}
    except Exception as e:
        print(f"❌ [Char Generation] Error: {e}")
        return {"status": "error", "error": str(e)}



@app.post("/api/image/generate-motion-from-image")
async def generate_motion_from_image(
    project_id: int = Body(...),
    scene_numbers: list = Body(...)   # 선택된 씬 번호 목록
):
    """생성된 이미지를 Gemini Vision으로 분석해 motion_desc 생성"""
    try:
        scene_prompts = db.get_image_prompts(project_id)
        if not scene_prompts:
            return {"status": "error", "error": "프롬프트가 없습니다."}

        targets = [p for p in scene_prompts if p.get('scene_number') in scene_numbers]
        if not targets:
            return {"status": "error", "error": "선택된 씬을 찾을 수 없습니다."}

        results = []
        errors = []

        for scene in targets:
            scene_num = scene.get('scene_number')
            image_url = scene.get('image_url') or ''
            scene_text = scene.get('scene_text') or scene.get('prompt_ko') or ''

            if not image_url:
                errors.append({"scene_number": scene_num, "error": "이미지가 없습니다. 먼저 이미지를 생성하세요."})
                continue

            # URL → 절대 경로 변환
            image_path = None
            if image_url.startswith("/static/"):
                rel = image_url.replace("/static/", "", 1).replace("/", os.sep)
                image_path = os.path.join(config.STATIC_DIR, rel)
            elif image_url.startswith("/output/"):
                rel = image_url.replace("/output/", "", 1).replace("/", os.sep)
                image_path = os.path.join(config.OUTPUT_DIR, rel)

            if not image_path or not os.path.exists(image_path):
                errors.append({"scene_number": scene_num, "error": f"이미지 파일을 찾을 수 없습니다: {image_url}"})
                continue

            try:
                print(f"🔍 [ImageMotion] Analyzing image for scene {scene_num}: {image_path}")
                motion = await gemini_service.generate_motion_desc_from_image(
                    image_path=image_path,
                    scene_text=scene_text
                )
                # DB 저장
                conn = db.get_db()
                conn.execute(
                    "UPDATE image_prompts SET motion_desc = ? WHERE project_id = ? AND scene_number = ?",
                    (motion, project_id, scene_num)
                )
                conn.commit()
                conn.close()

                results.append({"scene_number": scene_num, "motion_desc": motion})
                print(f"  ✅ Scene {scene_num}: {motion}")

            except Exception as e:
                print(f"  ❌ Scene {scene_num} vision failed: {e}")
                errors.append({"scene_number": scene_num, "error": str(e)})

        return {
            "status": "ok",
            "generated": len(results),
            "results": results,
            "errors": errors
        }

    except Exception as e:
        import traceback; traceback.print_exc()
        return {"status": "error", "error": str(e)}


@app.post("/api/image/bulk-generate-motion")
async def bulk_generate_motion(
    project_id: int = Body(...),
    max_scene: int = Body(5),        # 1~max_scene 씬까지 생성
    scene_numbers: list = Body(None) # 특정 씬만 지정 시 (없으면 1~max_scene)
):
    """씬 목록의 motion_desc(영상 모션 프롬프트)를 Gemini AI로 일괄 자동 생성"""
    try:
        scene_prompts = db.get_image_prompts(project_id)
        if not scene_prompts:
            return {"status": "error", "error": "프롬프트가 없습니다. 먼저 이미지 프롬프트를 생성해주세요."}

        # 대상 씬 결정
        if scene_numbers:
            targets = [p for p in scene_prompts if p.get('scene_number') in scene_numbers]
        else:
            targets = [p for p in scene_prompts if p.get('scene_number', 0) <= max_scene]

        if not targets:
            return {"status": "error", "error": f"씬 1~{max_scene} 범위에 데이터가 없습니다."}

        results = []
        errors = []

        for scene in targets:
            scene_num = scene.get('scene_number')
            scene_text = scene.get('scene_text') or scene.get('prompt_ko') or ''
            prompt_en  = scene.get('prompt_en') or ''

            try:
                print(f"🎬 [MotionGen] Generating motion_desc for scene {scene_num}...")
                motion = await gemini_service.generate_motion_desc(
                    scene_text=scene_text,
                    prompt_en=prompt_en
                )
                # DB 저장
                conn = db.get_db()
                conn.execute(
                    "UPDATE image_prompts SET motion_desc = ? WHERE project_id = ? AND scene_number = ?",
                    (motion, project_id, scene_num)
                )
                conn.commit()
                conn.close()

                results.append({"scene_number": scene_num, "motion_desc": motion})
                print(f"  ✅ Scene {scene_num}: {motion}")

            except Exception as e:
                print(f"  ❌ Scene {scene_num} failed: {e}")
                errors.append({"scene_number": scene_num, "error": str(e)})

        return {
            "status": "ok",
            "generated": len(results),
            "results": results,
            "errors": errors
        }

    except Exception as e:
        import traceback; traceback.print_exc()
        return {"status": "error", "error": str(e)}


@app.post("/api/image/generate")
async def generate_image(
    prompt: str = Body(...),
    project_id: int = Body(...),
    scene_number: int = Body(1),
    style: str = Body("realistic"),
    aspect_ratio: str = Body("16:9")
):
    """이미지를 생성하고 저장"""
    try:
        # Validate prompt
        if not prompt or not prompt.strip():
            print(f"❌ [Image Generation] Empty prompt for project {project_id}, scene {scene_number}")
            return {"status": "error", "error": "프롬프트가 비어있습니다. 먼저 프롬프트를 생성해주세요."}

        if len(prompt) > 5000:
            print(f"⚠️ [Image Generation] Prompt too long ({len(prompt)} chars), truncating...")
            prompt = prompt[:5000]

        print(f"🎨 [Image Generation] Starting for project {project_id}, scene {scene_number}")
        print(f"   Prompt: {prompt[:100]}...")
        print(f"   Aspect ratio: {aspect_ratio}")

        # 이미지 생성 전략
        images_bytes = None
        is_wimpy_style = any(kw in style.lower() for kw in ["wimpy", "stick", "졸라맨"]) or \
                         any(kw in prompt.lower() for kw in ["teal-blue hoodie", "cyan tunic", "cyan sleeveless", "stick figure cartoon", "white glove hand"])

        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # [2-PROMPT COMPOSITE MODE] 졸라맨 스타일: 캐릭터+배경 분리 생성 후 합성
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        if is_wimpy_style:
            # DB에서 해당 씬의 prompt_char, prompt_bg 조회
            scene_prompts = db.get_image_prompts(project_id)
            scene_data = next((s for s in scene_prompts if s.get('scene_number') == scene_number), None)
            prompt_char = scene_data.get('prompt_char', '') if scene_data else ''
            prompt_bg = scene_data.get('prompt_bg', '') if scene_data else ''

            if prompt_char and prompt_bg:
                print(f"🎨 [Image Gen] Wimpy COMPOSITE mode — generating character + background separately...")

                async def _generate_single(p: str) -> bytes | None:
                    """단일 프롬프트로 이미지 생성 (Replicate → Gemini → AKOOL 폴백)"""
                    result = None
                    try:
                        result = await replicate_service.generate_image(prompt=p, aspect_ratio="1:1")
                    except Exception as e:
                        print(f"⚠️ [Composite] Replicate failed: {e}")
                    if not result:
                        try:
                            result = await gemini_service.generate_image(prompt=p, num_images=1, aspect_ratio="1:1")
                        except Exception as e:
                            print(f"⚠️ [Composite] Gemini failed: {e}")
                    if not result:
                        try:
                            result = await akool_service.generate_image(prompt=p, aspect_ratio="1:1")
                        except Exception as e:
                            print(f"⚠️ [Composite] AKOOL failed: {e}")
                    return result[0] if result else None

                # 캐릭터 이미지 생성
                char_bytes = await _generate_single(prompt_char)
                # 배경 이미지 생성
                bg_bytes = await _generate_single(prompt_bg)

                if char_bytes and bg_bytes:
                    print(f"✅ [Composite] Both images generated — compositing...")
                    try:
                        composite_bytes = video_service.composite_character_on_background(
                            char_bytes=char_bytes,
                            bg_bytes=bg_bytes,
                            aspect_ratio=aspect_ratio,
                        )
                        images_bytes = [composite_bytes]
                        print(f"✅ [Composite] Compositing complete, size: {len(composite_bytes)} bytes")
                    except Exception as e:
                        print(f"⚠️ [Composite] Compositing failed: {e} — falling back to single-prompt mode")
                        images_bytes = None
                else:
                    print(f"⚠️ [Composite] Image generation partially failed (char={bool(char_bytes)}, bg={bool(bg_bytes)}) — falling back to single-prompt mode")

        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # [SINGLE-PROMPT MODE] 기본 단일 프롬프트 생성 (또는 합성 실패 시 폴백)
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

        # 윔피 스타일: 폴백 시에도 반드시 캐릭터 제약 prefix 추가
        # (Replicate is_wimpy 감지 보장 + Gemini/AKOOL 스타일 오염 방지)
        effective_prompt = prompt
        if is_wimpy_style:
            wimpy_char_prefix = (
                "YouTube educational cartoon illustration, stick-figure style character, "
                "teal-blue hoodie, black pants, white sneakers, round white head, dot eyes, "
                "NO necktie, NO suit, NO blue hair, NO business attire, bold black outlines, flat colors, "
            )
            # 이미 wimpy 키워드가 있으면 중복 추가 안 함
            if "teal-blue hoodie" not in prompt.lower() and "stick-figure" not in prompt.lower():
                effective_prompt = wimpy_char_prefix + prompt
                print(f"🎨 [Image Gen] Wimpy prefix injected into fallback prompt")

        if not images_bytes:
            if is_wimpy_style:
                print(f"🎨 [Image Gen] Wimpy style (single-prompt fallback) — Attempting Replicate Flux Dev...")
            else:
                print(f"🎨 [Image Gen] Attempting Replicate (Primary)...")
            try:
                images_bytes = await replicate_service.generate_image(prompt=effective_prompt, aspect_ratio=aspect_ratio)
            except Exception as e:
                print(f"⚠️ [Image Gen] Replicate failed: {e}")

        # 공통 폴백: Gemini Imagen
        if not images_bytes:
            try:
                print(f"🎨 [Image Gen] Attempting Gemini Imagen (Fallback)...")
                images_bytes = await gemini_service.generate_image(
                    prompt=effective_prompt,
                    num_images=1,
                    aspect_ratio=aspect_ratio
                )
            except Exception as e:
                print(f"⚠️ [Image Gen] Gemini failed: {e}")

        # 최종 폴백: AKOOL
        if not images_bytes:
            try:
                print(f"🎨 [Image Gen] Attempting AKOOL (Final Fallback)...")
                images_bytes = await akool_service.generate_image(prompt=effective_prompt, aspect_ratio=aspect_ratio)
            except Exception as e:
                print(f"⚠️ [Image Gen] AKOOL failed: {e}")

        if not images_bytes:
            return {"status": "error", "error": "모든 이미지 생성 서비스가 실패했습니다."}
        
        print(f"✅ [Image Generation] Successfully generated image, size: {len(images_bytes[0])} bytes")
        
        # 프로젝트별 폴더 경로 가져오기
        output_dir, web_dir = get_project_output_dir(project_id)
        
        filename = f"p{project_id}_s{scene_number}_{int(datetime.datetime.now().timestamp())}.png"
        output_path = os.path.join(output_dir, filename)
        
        # 파일 저장
        with open(output_path, "wb") as f:
            f.write(images_bytes[0])
        
        print(f"💾 [Image Generation] Saved to: {output_path}")
            
        image_url = f"{web_dir}/{filename}"
        
        # DB 업데이트 (이미지 URL 저장)
        print(f"💿 [Image Generation] Updating DB for Project {project_id}, Scene {scene_number} with URL {image_url}")
        db.update_image_prompt_url(project_id, scene_number, image_url)
        
        return {
            "status": "ok",
            "image_url": image_url
        }

    except Exception as e:
        error_details = f"이미지 생성 실패: {str(e)}"
        print(f"❌ [Image Generation] {error_details}")
        import traceback
        traceback.print_exc()
        return {"status": "error", "error": error_details}

@app.post("/api/projects/{project_id}/thumbnail/save")
async def save_project_thumbnail(
    project_id: int,
    file: UploadFile = File(...)
):
    """썸네일 이미지 저장 (Canvas에서 Blob으로 전송됨)"""
    try:
        # 파일 저장 경로 설정
        # thumbnails 폴더 별도 관리 또는 output 폴더 사용
        # 여기서는 관리 편의상 /static/thumbnails/{project_id} 사용
        upload_dir = os.path.join(config.STATIC_DIR, "thumbnails", str(project_id))
        os.makedirs(upload_dir, exist_ok=True)
        
        # 파일명 생성 (Timestamp)
        import time
        timestamp = int(time.time())
        filename = f"thumbnail_{timestamp}.png"
        file_path = os.path.join(upload_dir, filename)
        
        # 파일 저장
        with open(file_path, "wb") as buffer:
            import shutil
            shutil.copyfileobj(file.file, buffer)
            
        # 웹 접근 URL 생성
        # /static/thumbnails/{project_id}/{filename}
        web_url = f"/static/thumbnails/{project_id}/{filename}".replace(os.path.sep, '/')
        
        # DB 업데이트
        # 1. project_settings의 thumbnail_url 업데이트
        db.update_project_setting(project_id, "thumbnail_url", web_url)
        db.update_project_setting(project_id, "thumbnail_path", file_path) # 로컬 경로도 저장
        
        # 2. 프로젝트 메타정보 업데이트 (선택)
        # db.update_project(project_id, thumbnail_url=web_url) # 만약 projects 테이블에 컬럼이 있다면
        
        print(f"Thumbnail saved for project {project_id}: {web_url}")
        
        return {
            "status": "ok",
            "url": web_url,
            "path": file_path
        }
        
    except Exception as e:
        print(f"Thumbnail save error: {e}")
        import traceback
        traceback.print_exc()
        return JSONResponse(status_code=500, content={"error": str(e)})

@app.post("/api/projects/{project_id}/setting")
async def update_project_setting_api(project_id: int, req: ProjectSettingUpdate):
    """프로젝트 설정 단일 업데이트"""
    try:
        success = db.update_project_setting(project_id, req.key, req.value)
        if success:
            return {"status": "ok"}
        else:
            return {"status": "error", "error": "Invalid key or database error"}
    except Exception as e:
         return {"status": "error", "error": str(e)}

# ===========================================
# API: 미디어 관리 (모듈화 완료)
# ===========================================
from app.routers import media as media_router
app.include_router(media_router.router)

@app.post("/api/video/search")
async def search_stock_video(
    script: str = Body(None),
    style: str = Body("cinematic"),
    query: str = Body(None) # Direct query override
):
    """
    Pexels Stock Video 검색 API
    1. query가 있으면 바로 검색
    2. script가 있으면 Gemini에게 검색어 추출 요청 후 검색
    """
    from services.pexels_service import pexels_service
    
    search_query = query
    if not search_query and script:
         # Gemini에게 Pexels용 검색어 생성 요청
         search_query = await gemini_service.generate_video_search_keywords(script, style)
    
    if not search_query:
        search_query = "nature loop background" # Default

    result = pexels_service.search_videos(search_query, per_page=12) # Grid 3x4
    
    # Add Search Keyword to response for UI feedback
    if result.get("status") == "ok":
        result["search_query"] = search_query
        
    return result

@app.post("/api/video/generate-veo")
async def generate_veo_video(request: dict = Body(...)):
    """
    Google Veo Video Generation API
    """
    prompt = request.get("prompt")
    model = request.get("model", "veo-3.1-generate-preview")
    
    if not prompt:
        raise HTTPException(400, "Prompt is required")
        
    # Check API key configuration (generic check)
    if not config.GEMINI_API_KEY:
         return {"status": "error", "error": "GEMINI_API_KEY not configured"}

    # Call Service
    # Note: This is a long-running operation (polling included). 
    # Ideally should be a background task, but for MVP we wait.
    # If it takes > 60s, browser might timeout. We might need async task logic later.
    # Veo preview generation is usually fast (~10-20s).
    
    result = await gemini_service.generate_video(prompt, model)
    return result

# ===========================================
# API: 인트로 영상 업로드/삭제
# ===========================================

@app.post("/api/video/upload-intro/{project_id}")
async def upload_intro_video(
    project_id: int,
    file: UploadFile = File(...)
):
    """인트로 영상 업로드"""
    import shutil
    from pathlib import Path
    
    # 파일 확장자 검증
    allowed_extensions = {'.mp4', '.mov', '.avi', '.mkv', '.webm'}
    file_ext = Path(file.filename).suffix.lower()
    
    if file_ext not in allowed_extensions:
        raise HTTPException(400, f"지원하지 않는 파일 형식입니다. 허용: {', '.join(allowed_extensions)}")
    
    # 파일 크기 제한 (100MB)
    max_size = 100 * 1024 * 1024
    file.file.seek(0, 2)
    file_size = file.file.tell()
    file.file.seek(0)
    
    if file_size > max_size:
        raise HTTPException(400, "파일 크기는 100MB를 초과할 수 없습니다.")
    
    # 저장 경로 생성
    intro_dir = Path("uploads") / "intros" / str(project_id)
    intro_dir.mkdir(parents=True, exist_ok=True)
    
    # 파일 저장
    intro_path = intro_dir / f"intro{file_ext}"
    
    try:
        with intro_path.open("wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        
        # Web URL 생성 (Unix Style Path for URL)
        # /uploads/intros/{project_id}/intro{file_ext}
        web_url = f"/uploads/intros/{project_id}/intro{file_ext}"

        # 데이터베이스에 경로 저장 (intro_video_path AND background_video_url)
        conn = database.get_db()
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE project_settings 
            SET intro_video_path = ?, updated_at = CURRENT_TIMESTAMP
            WHERE project_id = ?
        """, (str(intro_path), project_id))
        conn.commit()
        conn.close()
        
        return {
            "status": "success",
            "intro_path": str(intro_path),
            "url": web_url,
            "file_size": file_size,
            "message": "인트로 영상이 업로드되었습니다."
        }
    except Exception as e:
        if intro_path.exists():
            intro_path.unlink()
        raise HTTPException(500, f"업로드 실패: {str(e)}")

@app.delete("/api/video/delete-intro/{project_id}")
async def delete_intro_video(project_id: int):
    """인트로 영상 삭제"""
    from pathlib import Path
    
    conn = database.get_db()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT intro_video_path FROM project_settings WHERE project_id = ?
    """, (project_id,))
    row = cursor.fetchone()
    
    if not row or not row[0]:
        conn.close()
        raise HTTPException(404, "인트로 영상이 없습니다.")
    
    intro_path = Path(row[0])
    
    try:
        if intro_path.exists():
            intro_path.unlink()
        
        cursor.execute("""
            UPDATE project_settings 
            SET intro_video_path = NULL, updated_at = CURRENT_TIMESTAMP
            WHERE project_id = ?
        """, (project_id,))
        conn.commit()
        conn.close()
        
        return {
            "status": "success",
            "message": "인트로 영상이 삭제되었습니다."
        }
    except Exception as e:
        conn.close()
        raise HTTPException(500, f"삭제 실패: {str(e)}")

# ===========================================
# ===========================================
# API: 영상 생성
# ===========================================



class RenderRequest(BaseModel):
    project_id: Union[int, str]
    use_subtitles: bool = True
    resolution: str = "1080p" # 1080p or 720p

class SubtitleGenerationRequest(BaseModel):
    project_id: Union[int, str]
    text: Optional[str] = None











# ===========================================
# Subtitle Routes
# ===========================================

@app.get("/subtitle-gen", response_class=HTMLResponse)
async def subtitle_gen_page(request: Request, project_id: Optional[int] = None):
    print(f"DEBUG LOG: Serving subtitle_gen.html. PID={project_id}")
    
    project = None
    if project_id:
        project = db.get_project(project_id)
        
    return templates.TemplateResponse("pages/subtitle_gen.html", {
        "request": request,
        "project": project,
        "title": "자막 생성 및 편집",
        "page": "subtitle-gen"
    })




@app.post("/api/project/{project_id}/subtitle/delete")
async def delete_subtitle_segment(
    project_id: int,
    request: dict = Body(...)
):
    """자막 삭제 및 오디오 싱크 맞춤 (Destructive)"""
    try:
        index = request.get('index')
        start = request.get('start')
        end = request.get('end')
        
        # 1. 자막 로드
        settings = db.get_project_settings(project_id)
        subtitle_path = settings.get('subtitle_path')
        if not subtitle_path or not os.path.exists(subtitle_path):
             return {"status": "error", "error": "자막 파일이 없습니다"}
             
        import json
        with open(subtitle_path, "r", encoding="utf-8") as f:
            subtitles = json.load(f)
            
        if index < 0 or index >= len(subtitles):
            return {"status": "error", "error": "잘못된 자막 인덱스"}
            
        # 2. 오디오 자르기 (서비스 호출)
        audio_data = db.get_tts(project_id)
        if audio_data and audio_data.get('audio_path'):
            from services.audio_service import audio_service
            audio_service.cut_audio_segment(audio_data['audio_path'], start, end)
            
        # 3. 자막 리스트 업데이트 (삭제 및 시간 시프트)
        deleted_duration = end - start
        
        # 삭제
        subtitles.pop(index)
        
        # 이후 자막들 당기기
        for sub in subtitles:
            if sub['start'] >= end:
                sub['start'] -= deleted_duration
                sub['end'] -= deleted_duration
                # 부동소수점 오차 보정 (0보다 작아지지 않게)
                sub['start'] = max(0, sub['start'])
                sub['end'] = max(0, sub['end'])
                
        # 4. 저장
        with open(subtitle_path, "w", encoding="utf-8") as f:
            json.dump(subtitles, f, ensure_ascii=False, indent=2)
            
        # 5. 미리보기 재생성 (간소화: 여기서 다시 로직을 태우기보다 프론트에서 save 호출 유도하거나, 여기서 일부만 업데이트)
        # 일단은 데이터만 반환하고 프론트가 렌더링하도록 함. 
        # (완벽하려면 save_subtitle 로직처럼 preview image도 갱신해야 하나, 시간 단축 위해 생략 가능. 
        #  단, preview image가 기존 것과 꼬일 수 있음. -> 클라이언트가 reload 시 해결됨)
        
        return {
            "status": "ok",
            "subtitles": subtitles,
            "message": f"자막 삭제 완료 (오디오 {deleted_duration:.2f}초 단축됨)"
        }
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        return {"status": "error", "error": str(e)}
        



@app.post("/api/project/{project_id}/subtitle/regenerate")
async def regenerate_subtitles(project_id: int):
    """자막 AI 재분석 (싱크 맞추기)"""
    try:
        # 1. 오디오 경로 확인
        audio_data = db.get_tts(project_id)
        if not audio_data or not audio_data.get('audio_path') or not os.path.exists(audio_data['audio_path']):
            return {"status": "error", "error": "오디오 파일이 없습니다."}
            
        audio_path = audio_data['audio_path']
        
        # 2. 대본 데이터 (힌트용)
        script_data = db.get_script(project_id)
        script_text = script_data.get("full_script") if script_data else ""
        
        # [DEBUG] Log script text
        try:
            with open("debug_script_log.txt", "w", encoding="utf-8") as f:
                f.write(f"ProjectID: {project_id}\n")
                f.write(f"ScriptText (Len={len(script_text)}):\n{script_text}\n")
        except:
            pass
        
        # 3. 기존 자막/VTT 무시하고 강제 생성
        from services.video_service import video_service
        print(f"Force regenerating subtitles for {project_id}...")
        
        new_subtitles = video_service.generate_aligned_subtitles(audio_path, script_text)
        
        if not new_subtitles:
            return {"status": "error", "error": "AI 자막 생성 실패"}
            
        # 4. 저장
        inner_output_dir, _ = get_project_output_dir(project_id)
        saved_sub_path = os.path.join(inner_output_dir, f"subtitles_{project_id}.json")
        
        import json
        with open(saved_sub_path, "w", encoding="utf-8") as f:
            json.dump(new_subtitles, f, ensure_ascii=False, indent=2)
            
        return {
            "status": "ok",
            "subtitles": new_subtitles,
            "message": "자막이 AI로 재분석되었습니다."
        }
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        return {"status": "error", "error": str(e)}


@app.get("/autopilot", response_class=HTMLResponse)
async def page_autopilot(request: Request):
    """오토파일럿 (디렉터 모드) 페이지"""
    return templates.TemplateResponse("pages/autopilot.html", {"request": request})

class AutoPilotStartRequest(BaseModel):
    keyword: Optional[str] = None
    topic: Optional[str] = None
    visual_style: str = "realistic"
    thumbnail_style: Optional[str] = "face"
    video_scene_count: Optional[int] = 0
    all_video: Optional[bool] = False
    video_engine: Optional[str] = "wan" # "wan" or "akool"
    motion_method: Optional[str] = "standard"
    narrative_style: str = "informative"
    script_style: Optional[str] = None
    voice_id: str = "ko-KR-Neural2-A"
    voice_provider: Optional[str] = None
    subtitle_style: str = "Basic_White"
    duration_seconds: Optional[int] = 0
    subtitle_settings: Optional[Dict[str, Any]] = None
    preset_id: Optional[int] = None

@app.get("/api/settings/subtitle/defaults")
async def get_subtitle_defaults_api():
    """최근 사용된(또는 기본) 자막 설정 반환 (오토파일럿 UI 표시용)"""
    try:
        defaults = db.get_subtitle_defaults()
        return {"status": "ok", "settings": defaults}
    except Exception as e:
        return {"status": "error", "error": str(e)}


# ===========================================
# API: Autopilot Presets (Saved Configurations)
# ===========================================

class AutopilotPresetSave(BaseModel):
    name: str
    settings: dict

@app.get("/api/autopilot/presets")
async def get_autopilot_presets_api():
    presets = db.get_autopilot_presets()
    # Parse JSON for frontend
    for p in presets:
        try:
            p['settings'] = json.loads(p['settings_json'])
        except:
            p['settings'] = {}
    return {"status": "ok", "presets": presets}

@app.post("/api/autopilot/presets")
async def save_autopilot_preset_api(req: AutopilotPresetSave):
    try:
        db.save_autopilot_preset(req.name, req.settings)
        return {"status": "ok"}
    except Exception as e:
        return {"status": "error", "error": str(e)}

@app.delete("/api/autopilot/presets/{preset_id}")
async def delete_autopilot_preset_api(preset_id: int):
    try:
        db.delete_autopilot_preset(preset_id)
        return {"status": "ok"}
    except Exception as e:
        return {"status": "error", "error": str(e)}

@app.post("/api/autopilot/start")

async def start_autopilot_api(
    req: AutoPilotStartRequest,
    background_tasks: BackgroundTasks
):
    """오토파일럿 시작 (API)"""
    # 1. Preset Loading
    if req.preset_id:
        presets = db.get_autopilot_presets()
        preset = next((p for p in presets if p['id'] == req.preset_id), None)
        if preset:
             try:
                 p_settings = json.loads(preset['settings_json'])
                 # Apply preset values if req fields are default
                 # For now, simplistic merge: req overrides preset if set (we assume frontend handles this mostly)
                 # Actually, let's trust the frontend to send the merged config if they selected a preset.
                 # But if they send preset_id, we might want to load subtitle_settings from it if missing.
                 if not req.subtitle_settings:
                     req.subtitle_settings = p_settings.get("subtitle_settings")
             except: pass

    # 2. Topic Resolve
    topic = req.topic or req.keyword
    if not topic:
         return {"status": "error", "error": "Topic (or keyword) is required"}

    # 3. Start Workflow in Background
    config_dict = {
        "visual_style": req.visual_style,
        "thumbnail_style": req.thumbnail_style,
        "video_scene_count": req.video_scene_count,
        "all_video": req.all_video,
        "video_engine": req.video_engine,
        "motion_method": req.motion_method,
        "narrative_style": req.script_style or req.narrative_style,
        "script_style": req.script_style or req.narrative_style, 
        "voice_id": req.voice_id,
        "voice_provider": req.voice_provider,
        "subtitle_style": req.subtitle_style,
        "duration_seconds": req.duration_seconds,
        "subtitle_settings": req.subtitle_settings 
    }
    
    # Create Project First
    project_name = f"[Auto] {topic}"
    project_id = db.create_project(name=project_name, topic=topic)
    
    # Save Initial Settings
    db.update_project_setting(project_id, "autopilot_config", config_dict)
    
    # Apply Subtitle Settings from Preset/Request
    if req.subtitle_settings:
        db.save_project_settings(project_id, req.subtitle_settings)
        print(f"✅ Applied custom subtitle settings to Project {project_id}")

    # [NEW] Also save key settings to project_settings table directly for immediate UI sync
    if req.thumbnail_style:
        db.update_project_setting(project_id, "thumbnail_style", req.thumbnail_style)
    if req.duration_seconds:
         db.update_project_setting(project_id, "duration_seconds", req.duration_seconds)
    if req.script_style:
         db.update_project_setting(project_id, "script_style", req.script_style)
    if req.visual_style:
         db.update_project_setting(project_id, "image_style", req.visual_style) # Sync
         db.update_project_setting(project_id, "visual_style", req.visual_style)
    
    from services.autopilot_service import autopilot_service
    # Start Task
    background_tasks.add_task(autopilot_service.run_workflow, topic, project_id, config_dict)
    
    return {"status": "ok", "project_id": project_id, "message": "Automation started"}

# ===========================================
# Auto-Pilot Scheduler
# ===========================================
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from services.autopilot_service import autopilot_service

scheduler = BackgroundScheduler()

@app.on_event("startup")
def start_scheduler():
    scheduler.start()
    print("[Scheduler] 스케줄러가 시작되었습니다.")

@app.on_event("shutdown")
def shutdown_scheduler():
    scheduler.shutdown()

@app.post("/api/autopilot/schedule")
async def schedule_autopilot(
    keyword: str = Form(...),
    hour: int = Form(...),
    minute: int = Form(...)
):
    """오토파일럿 예약 (매일 해당 시간에 실행)"""
    
    # 기존 작업 제거 (단일 작업만 허용할 경우)
    scheduler.remove_all_jobs()
    
    # 새 작업 추가
    scheduler.add_job(
        lambda: asyncio.run(autopilot_service.run_workflow(keyword)),
        trigger=CronTrigger(hour=hour, minute=minute),
        id="autopilot_job",
        name=f"AutoPilot-{keyword}"
    )
    
    now_kst = config.get_kst_time()
    return {
        "status": "ok",
        "message": f"매일 {hour:02d}:{minute:02d}에 '{keyword}' 주제로 자동 제작이 예약되었습니다.",
        "server_time": now_kst.strftime("%H:%M")
    }

@app.post("/api/autopilot/run-now")
async def run_autopilot_now(
    background_tasks: BackgroundTasks,
    keyword: str = Form(...)
):
    """오토파일럿 즉시 실행 (테스트용)"""
    background_tasks.add_task(autopilot_service.run_workflow, keyword)
    return {"status": "started", "message": f"'{keyword}' 주제로 즉시 제작을 시작합니다."}

class AutopilotContinueRequest(BaseModel):
    auto_plan: bool = False
    topic: Optional[str] = None
    script_style: Optional[str] = None
    duration_seconds: Optional[int] = None

@app.post("/api/autopilot/continue/{project_id}")
async def continue_autopilot(
    project_id: int, 
    req: AutopilotContinueRequest,
    background_tasks: BackgroundTasks
):
    """기획 데이터 이어받아 오토파일럿 시작 (Step 4부터 혹은 기획부터)"""
    project = db.get_project(project_id)
    if not project: raise HTTPException(404, "Project not found")

    # Update settings if provided (Force Auto Plan)
    if req.auto_plan:
        if req.topic: db.update_project(project_id, topic=req.topic)
        
        settings_update = {}
        if req.script_style: settings_update["script_style"] = req.script_style
        if req.duration_seconds: settings_update["duration_seconds"] = req.duration_seconds
        
        for k, v in settings_update.items():
            db.update_project_setting(project_id, k, v)

    # Force 'analyzed' status to trigger Step 4 (Scripting) in Autopilot
    # Even for auto_plan, we need 'analyzed' status (analysis data) to be present.
    # Usually manual flow ensures analysis is done before entering script_plan page.
    if project.get("status") in ["created", "planning", "analyzed"]:
        db.update_project(project_id, status="analyzed")

    p_settings = db.get_project_settings(project_id) or {}
    config_dict = {
        "script_style": p_settings.get("script_style", "default"),
        "duration_seconds": p_settings.get("duration_seconds", 300),
        "voice_provider": p_settings.get("voice_provider"),
        "voice_id": p_settings.get("voice_id"),
        "visual_style": p_settings.get("visual_style", "realistic"), 
        "thumbnail_style": p_settings.get("thumbnail_style", "face"), 
        "all_video": bool(p_settings.get("all_video", 0)),
        "motion_method": p_settings.get("motion_method", "standard"),
        "video_scene_count": p_settings.get("video_scene_count", 0),
        "auto_thumbnail": True,
        "auto_plan": req.auto_plan
    }

    background_tasks.add_task(autopilot_service.run_workflow, project['topic'], project_id, config_dict)
    return {"status": "ok", "project_id": project_id}


# ===========================================
# ===========================================
# Render Progress API
# ===========================================
@app.get("/api/project/{project_id}/render/status")
async def get_render_status(project_id: int):
    """실시간 렌더링 진행률 조회"""
    from services.progress import get_render_progress
    return get_render_progress(project_id)

# ===========================================


# ===========================================
# 서버 실행 (Direct Run)
# ===========================================

# ===========================================
# API: Repository to Script Plan
# ===========================================

class RepositoryPlanRequest(BaseModel):
    title: str
    synopsis: str
    success_factor: str

@app.post("/api/repository/create-plan")
async def create_plan_from_repository(req: RepositoryPlanRequest):
    """
    저장소(Repository)의 분석 결과를 바탕으로
    1. 새 프로젝트 생성
    2. 대본 기획(Structure) 자동 생성
    """
    # 1. Create Project
    try:
        project_id = db.create_project(req.title, req.synopsis)
        print(f"Created Project for Plan: {req.title} ({project_id})")
    except Exception as e:
        raise HTTPException(500, f"프로젝트 생성 실패: {str(e)}")

    # 2. Prepare Mock Analysis Data for Gemini
    # Repository data provides minimal context, so we adapt it.
    analysis_simulation = {
        "topic": req.synopsis, # Use synopsis as the core topic
        "user_notes": f"Original Motivation (Success Factor): {req.success_factor}\nTarget Title: {req.title}",
        "duration": 600, # Default ~10 min
        "script_style": "story" # Default style
    }

    # 3. Generate Structure
    from services.gemini_service import gemini_service
    try:
        structure = await gemini_service.generate_script_structure(analysis_simulation)
        
        if "error" in structure:
            print(f"Structure Gen Warning: {structure['error']}")
        else:
            db.save_script_structure(project_id, structure)
            db.update_project(project_id, status="planned")
            
    except Exception as e:
        print(f"Structure Gen Error: {e}")
    
    return {"status": "ok", "project_id": project_id}



@app.post("/api/project/{project_id}/scan-assets")
async def scan_project_assets(project_id: int):
    """
    프로젝트 폴더를 스캔하여 DB에 누락된 오디오/이미지 자산을 수동으로 등록/복구합니다.
    """
    try:
        result = recover_project_assets(project_id)
        return {
            "status": "success", 
            "message": f"복구 완료: 오디오 {'있음' if result['audio'] else '없음'}, 이미지 {result['images']}장 복구됨"
        }
    except Exception as e:
        print(f"Scan assets error: {e}")
        return JSONResponse(status_code=500, content={"error": str(e)})

def recover_project_assets(project_id: int):
    """
    폴더 스캔 및 DB 복구 핵심 로직 (재사용 가능하도록 분리)
    Returns: {'audio': bool, 'images': int}
    """
    output_dir, _ = get_project_output_dir(project_id)
    recovered_audio = False
    recovered_images = 0
    
    # 1. 오디오 파일 스캔
    audio_filename = f"audio_{project_id}.mp3"
    audio_path = os.path.join(output_dir, audio_filename)
    
    if os.path.exists(audio_path):
        existing_tts = db.get_tts(project_id)
        if not existing_tts:
            print(f"Recovering audio for project {project_id}: {audio_path}")
            db_conn = db.get_connection()
            cursor = db_conn.cursor()
            cursor.execute(
                "INSERT INTO tts_audio (project_id, audio_path, duration, created_at) VALUES (?, ?, ?, ?)",
                (project_id, audio_path, 0, datetime.datetime.now().isoformat())
            )
            db_conn.commit()
            db_conn.close()
            recovered_audio = True

    # 2. 이미지 파일 스캔
    import glob
    image_pattern = os.path.join(output_dir, f"image_{project_id}_*.png")
    found_images = glob.glob(image_pattern)
    
    if found_images:
        db_conn = db.get_connection()
        cursor = db_conn.cursor()
        
        for img_path in found_images:
            filename = os.path.basename(img_path)
            try:
                parts = filename.replace(".png", "").split("_")
                if len(parts) >= 3:
                    scene_num = int(parts[2])
                    
                    cursor.execute("SELECT id FROM image_prompts WHERE project_id=? AND scene_number=?", (project_id, scene_num))
                    if not cursor.fetchone():
                        print(f"Recovering image for project {project_id} scene {scene_num}: {img_path}")
                        rel_path = os.path.relpath(img_path, config.OUTPUT_DIR)
                        web_url = f"/output/{rel_path}".replace("\\", "/")
                        
                        cursor.execute(
                            "INSERT INTO image_prompts (project_id, scene_number, prompt, image_path, image_url, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                            (project_id, scene_num, "Recovered Image", img_path, web_url, datetime.datetime.now().isoformat())
                        )
                        recovered_images += 1
            except Exception as e:
                print(f"Skipping malformed filename {filename}: {e}")
                
        db_conn.commit()
        db_conn.close()
        
    return {'audio': recovered_audio, 'images': recovered_images}
        

# ===========================================
# API: 외부 영상 업로드
# ===========================================






@app.post("/api/youtube/upload-external/{project_id}")
async def upload_external_to_youtube(
    project_id: int, 
    request: Request
):
    """업로드된 외부 영상 게시 (Standard: Private, Independent: Selectable)"""
    try:
        data = await request.json()
        requested_privacy = data.get("privacy", "private")
        requested_publish_at = data.get("publish_at")
        requested_channel_id = data.get("channel_id")
    except:
        requested_privacy = "private"
        requested_publish_at = None
        requested_channel_id = None

    # [NEW] Membership Check
    from services.auth_service import auth_service
    is_independent = auth_service.is_independent()
    
    # Force private if not independent
    final_privacy = "private"
    final_publish_at = None
    
    if is_independent:
        final_privacy = requested_privacy
        final_publish_at = requested_publish_at
        
        # YouTube requires 'private' for scheduled
        if final_publish_at:
            final_privacy = "private"
    else:
        # Standard user always private locally
        if requested_privacy == "public":
            print("[Security] Standard user attempted public upload. Forcing private.")
            final_privacy = "private"

    try:
        # 프로젝트 정보 조회
        project = db.get_project(project_id)
        if not project:
            raise HTTPException(404, "프로젝트를 찾을 수 없습니다.")
        
        # 영상 경로 조회 (외부 업로드 -> 렌더링 영상 순)
        settings = db.get_project_settings(project_id)
        video_path = settings.get('external_video_path')
        
        if not video_path or not os.path.exists(video_path):
            video_path = settings.get('video_path')
            
        # 렌더링 웹 경로 처리
        if video_path and not os.path.exists(video_path) and video_path.startswith('/output/'):
            rel_path = video_path.replace('/output/', '', 1).replace('/', os.sep)
            video_path = os.path.join(config.OUTPUT_DIR, rel_path)
            
        if not video_path or not os.path.exists(video_path):
            raise HTTPException(404, "업로드되거나 렌더링된 영상이 없습니다.")
        
        # YouTube 업로드 서비스 import
        from services.youtube_upload_service import youtube_upload_service
        
        # 메타데이터 조회 (title, description, tags)
        metadata = db.get_metadata(project_id)
        title = metadata.get('titles', [project['name']])[0] if metadata else project['name']
        description = metadata.get('description', '') if metadata else ''
        tags = metadata.get('tags', []) if metadata else []
        
        # [NEW] 채널 정보 조회하여 토큰 경로 결정
        token_path = None
        try:
            if requested_channel_id:
                channel = db.get_channel(requested_channel_id)
                if channel and channel.get('credentials_path'):
                    cand_path = channel['credentials_path']
                    if os.path.exists(cand_path):
                        token_path = cand_path
            
            if not token_path:
                # Fallback to first channel if not specified or not found
                channels = db.get_all_channels()
                if channels:
                    cand_path = channels[0].get('credentials_path')
                    if cand_path and os.path.exists(cand_path):
                        token_path = cand_path
        except Exception as e:
            print(f"[YouTube] Channel resolution error: {e}")
            token_path = None

        # YouTube 업로드 (동기 함수이므로 await 제거)
        result = youtube_upload_service.upload_video(
            file_path=video_path,
            title=title,
            description=description,
            tags=tags,
            category_id="22",  # People & Blogs
            privacy_status=final_privacy,
            publish_at=final_publish_at,
            token_path=token_path
        )
        
        if result and result.get('id'):
            video_id = result.get('id')
            
            # DB에 YouTube 비디오 ID 및 상태 저장
            db.update_project_setting(project_id, 'youtube_video_id', video_id)
            db.update_project_setting(project_id, 'is_published', 1)
            db.update_project_setting(project_id, 'is_uploaded', 1)
            
            return {
                "status": "ok",
                "video_id": video_id,
                "url": f"https://www.youtube.com/watch?v={video_id}"
            }
        else:
            raise HTTPException(500, result.get('error', 'YouTube 업로드 실패'))
            
    except Exception as e:
        print(f"YouTube upload error: {e}")
        import traceback
        traceback.print_exc()
        return {"status": "error", "error": f"YouTube 업로드 실패: {str(e)}"}




# ===========================================
# API: Repository to Script Plan
# ===========================================

class RepositoryPlanRequest(BaseModel):
    title: str
    synopsis: str
    success_factor: str

@app.post("/api/repository/create-plan")
async def create_plan_from_repository(req: RepositoryPlanRequest):
    """
    저장소(Repository)의 분석 결과를 바탕으로
    1. 새 프로젝트 생성
    2. 대본 기획(Structure) 자동 생성
    """
    # 1. Create Project
    try:
        project_id = db.create_project(req.title, req.synopsis)
        print(f"Created Project for Plan: {req.title} ({project_id})")
    except Exception as e:
        raise HTTPException(500, f"프로젝트 생성 실패: {str(e)}")

    # 2. Prepare Mock Analysis Data for Gemini
    # Repository data provides minimal context, so we adapt it.
    analysis_simulation = {
        "topic": req.synopsis, # Use synopsis as the core topic
        "user_notes": f"Original Motivation (Success Factor): {req.success_factor}\nTarget Title: {req.title}",
        "duration": 600, # Default ~10 min
        "script_style": "story" # Default style
    }

    # 3. Generate Structure
    from services.gemini_service import gemini_service
    try:
        structure = await gemini_service.generate_script_structure(analysis_simulation)
        
        if "error" in structure:
            print(f"Structure Gen Warning: {structure['error']}")
            return {"status": "error", "error": f"대본 구조 생성 실패: {structure['error']}", "project_id": project_id}
        else:
            db.save_script_structure(project_id, structure)
            db.update_project(project_id, status="planned")
            # Update Project Topic to match, just in case
            db.update_project(project_id, topic=req.synopsis)
            
    except Exception as e:
        print(f"Structure Gen Error: {e}")
        return {"status": "error", "error": f"AI 생성 중 오류: {str(e)}", "project_id": project_id}
    
    return {"status": "ok", "project_id": project_id}




# ===========================================
# API: 스타일 프리셋 관리 (모듈화 완료)
# ===========================================
from app.routers import settings as settings_router
from app.routers import thumbnails as thumbnails_router
app.include_router(settings_router.router)
app.include_router(thumbnails_router.router)



if __name__ == "__main__":
    print("=" * 50)
    print("PICADIRI STUDIO v2.0")
    print("-" * 50)

    config.validate()
    
    # Initialize & Migrate Database
    db.init_db()
    db.migrate_db()
    
    # [NEW] Verify License & Membership
    from services.auth_service import auth_service
    auth_service.verify_license()
    
    # [NEW] Auto-open Browser in Production (or Frozen)
    if not config.DEBUG or getattr(sys, 'frozen', False):
        import webbrowser
        import threading
        import time
        
        def open_browser():
            time.sleep(1.5) # Wait for server startup
            webbrowser.open(f"http://{config.HOST}:{config.PORT}")
            
        print("브라우저 자동 실행 대기 중...")
        threading.Thread(target=open_browser, daemon=True).start()

    # [NEW] Auto Publish Service Start
    from services.auto_publish_service import auto_publish_service
    auto_publish_service.start()

    print(f"[*] 서버 시간(KST): {config.get_kst_time().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"[*] 서버 주소: http://{config.HOST}:{config.PORT}")
    print("=" * 50)

    uvicorn.run(
        "main:app",
        host=config.HOST,
        port=config.PORT,
        reload=config.DEBUG,
        log_level="info"
    )

