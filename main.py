"""
PICADILLY STUDIO - FastAPI 메인 서버
YouTube 영상 자동화 제작 플랫폼 (Python 기반)
[RELOAD TRIGGER] 2026-04-17 v3 (HTML Response)
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

# PyInstaller console=False(창 없는 GUI) 빌드에서는 콘솔이 아예 없어서
# sys.stdout/sys.stderr가 None이 된다. uvicorn 등 일부 라이브러리가 로깅 설정 중
# sys.stdout.isatty()를 호출해 AttributeError로 죽는 문제(백그라운드 서버 스레드가
# 포트 바인딩도 하기 전에 조용히 크래시)가 있었으므로, None인 경우 더미 스트림으로 채운다.
if sys.stdout is None:
    sys.stdout = open(os.devnull, 'w', encoding='utf-8', errors='replace')
if sys.stderr is None:
    sys.stderr = open(os.devnull, 'w', encoding='utf-8', errors='replace')

# Windows 콘솔/태스크바 아이콘을 클래퍼보드(🎬)로 변경
def _set_window_icon():
    if sys.platform != 'win32':
        return
    try:
        import ctypes
        icon_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static", "img", "air_studio.ico")
        if not os.path.exists(icon_path):
            return
        HWND = ctypes.windll.kernel32.GetConsoleWindow()
        if not HWND:
            return
        hIcon = ctypes.windll.user32.LoadImageW(None, icon_path, 1, 0, 0, 0x0010 | 0x0040)
        if hIcon:
            ctypes.windll.user32.SendMessageW(HWND, 0x0080, 1, hIcon)  # WM_SETICON ICON_BIG
            ctypes.windll.user32.SendMessageW(HWND, 0x0080, 0, hIcon)  # WM_SETICON ICON_SMALL
    except Exception:
        pass

_set_window_icon()

from fastapi import FastAPI, Request, HTTPException, Form, BackgroundTasks, Body, Query, UploadFile, File
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional, Dict, Any, Union
import uvicorn
import httpx
import time
import pykakasi

# Initialize kakasi globally
kakasi = pykakasi.kakasi()
import asyncio
import json
import re
import datetime
import aiofiles
import shutil


# ==========================================
# FFmpeg & Pydub Configuration (Global)
# ==========================================
try:
    from pydub import AudioSegment
    import glob

    ffmpeg_candidates = []
    if os.getenv("IMAGEIO_FFMPEG_EXE"):
        ffmpeg_candidates.append(os.getenv("IMAGEIO_FFMPEG_EXE"))
    ffmpeg_candidates.extend(glob.glob(os.path.join(os.getcwd(), "venv", "Lib", "site-packages", "imageio_ffmpeg", "binaries", "ffmpeg*.exe")))
    if shutil.which("ffmpeg"):
        ffmpeg_candidates.append(shutil.which("ffmpeg"))

    ffmpeg_path = next((p for p in ffmpeg_candidates if p and os.path.exists(p)), None)
    if not ffmpeg_path:
        import imageio_ffmpeg
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
from services.gemini_service import gemini_service
from services.auth_service import auth_service
from services.drive_bundle_service import drive_bundle_service
from services.web_admin_client import web_admin_client
from services.topic_queue_sync_service import sync_topic_progress
from services.project_sync_service import sync_project_metadata

# 공유 헬퍼/상수 — app/utils.py 에서 임포트
from app.utils import (
    validate_upload as _validate_upload,
    get_project_output_dir,
    ALLOWED_AUDIO_EXT as _ALLOWED_AUDIO_EXT,
    ALLOWED_VIDEO_EXT as _ALLOWED_VIDEO_EXT,
    ALLOWED_IMAGE_EXT as _ALLOWED_IMAGE_EXT,
    MAX_AUDIO_SIZE as _MAX_AUDIO_SIZE,
    MAX_VIDEO_SIZE as _MAX_VIDEO_SIZE,
    MAX_IMAGE_SIZE as _MAX_IMAGE_SIZE,
)
from app.modes import DEFAULT_APP_MODE, normalize_app_mode


# FastAPI 앱 생성
app = FastAPI(
    title="피카딜리스튜디오",
    description="AI 기반 YouTube 영상 자동화 제작 플랫폼",
    version="2.0.0"
)


def _queue_project_sync(background_tasks: BackgroundTasks, project_id: int):
    """프로젝트 저장 후 Supabase 메타데이터 동기화를 best-effort로 예약."""
    try:
        if background_tasks is not None and project_id:
            background_tasks.add_task(sync_project_metadata, project_id)
    except Exception as e:
        print(f"[ProjectSync] Queue warning for {project_id}: {e}")


from fastapi.responses import RedirectResponse

# [AIR-0133] Per-request language resolution helpers
_LANG_ALLOWED = {"ko", "en", "vi", "th"}

def _resolve_request_lang(request: Request) -> str:
    """Determine the UI language for this request.
    Priority: cookie "language" > server default (app_lang) > "en"
    """
    cookie_lang = request.cookies.get("language")
    if cookie_lang in _LANG_ALLOWED:
        return cookie_lang
    return app_lang if app_lang in _LANG_ALLOWED else "en"


# 직원 로그인 & 멀티유저 세션 관리 미들웨어
@app.middleware("http")
async def check_login_middleware(request: Request, call_next):
    try:
        path = request.url.path

        # 예외 대상 경로 리스트 (로그인, API 인증, 헬스체크 등)
        bypass_paths = [
            "/login",
            "/api/auth/login",
            "/api/auth/emails",
            "/api/health",
        ]

        # static, uploads, favicon, docs 등의 정적 에셋 경로 우회
        is_asset = (
            path.startswith("/static") or
            path.startswith("/output") or
            path.startswith("/uploads") or
            path.startswith("/assets") or
            path.startswith("/favicon.ico") or
            path.startswith("/docs") or
            path.startswith("/openapi.json")
        )

        # HTML 페이지 요청인지 확인 (수동 주소창 접근 시 리디렉션하기 위함)
        accept_header = request.headers.get("accept") or ""
        is_html_request = "text/html" in accept_header

        # 로그인 체크 적용 대상인 경우
        if not is_asset and not any(path == bp for bp in bypass_paths) and is_html_request:
            user_email = request.cookies.get("user_email")
            if not user_email:
                return RedirectResponse(url="/login")
            else:
                # auth_service의 active user 이메일 및 에셋 폴더 동적 활성화
                # [AIR-0225B Batch A] desktop_session_token 쿠키가 있으면
                # /api/desktop-resync로 비밀번호 없이 안전하게 세션을 재개한다
                # (service_role 불필요). 없으면(구버전 세션 등) 기존 폴백 동작.
                from services.auth_service import auth_service
                session_token = request.cookies.get("desktop_session_token")
                auth_service.login_user(user_email, session_token=session_token)

        # [AIR-0133] Per-request language: set on request.state for all routes
        # Routers read request.state.current_lang instead of global app_lang.
        # API routes (non-HTML) also get this set so they can pass it to
        # background tasks if needed, though most don't use it.
        request.state.current_lang = _resolve_request_lang(request)

        response = await call_next(request)
        return response
    except Exception as e:
        import traceback
        print("CRITICAL: Error in check_login_middleware!")
        traceback.print_exc()
        try:
            with open(config.DEBUG_LOG_PATH, "a", encoding="utf-8") as rf:
                rf.write(f"[{datetime.datetime.now()}] Middleware Error: {e}\n{traceback.format_exc()}\n")
        except Exception:
            pass
        raise e

# [AIR-0137] /output 파일 서빙 — .mp4는 로그인 필수, path traversal 차단
@app.get("/output/{file_path:path}")
async def serve_output_file(file_path: str):
    from services.auth_service import auth_service

    if file_path.startswith("external/"):
        rel = file_path.replace("external/", "", 1)
        appdata_base = config.LOCAL_APP_DATA_DIR
        abs_path = os.path.normpath(os.path.join(appdata_base, rel))
        norm_base = os.path.normpath(appdata_base)
        if not (abs_path == norm_base or abs_path.startswith(norm_base + os.sep)):
            raise HTTPException(status_code=403, detail="Access denied.")
        if not os.path.exists(abs_path):
            raise HTTPException(status_code=404, detail="File not found")
        if abs_path.lower().endswith(".mp4"):
            if not auth_service.get_user_email():
                raise HTTPException(status_code=403, detail="Login required to access video files.")
        return FileResponse(abs_path)

    full_path = os.path.join(config.OUTPUT_DIR, file_path)
    norm_output = os.path.normpath(config.OUTPUT_DIR)
    norm_full = os.path.normpath(full_path)
    if not (norm_full == norm_output or norm_full.startswith(norm_output + os.sep)):
        raise HTTPException(status_code=403, detail="Access denied.")
    if not os.path.exists(full_path):
        raise HTTPException(status_code=404, detail="File not found")
    if full_path.lower().endswith(".mp4"):
        if not auth_service.get_user_email():
            raise HTTPException(status_code=403, detail="Login required to access video files.")
    return FileResponse(full_path)

# [NEW] 실시간 등급/토큰 동기화 API
# CORS 설정 (로컬 앱 전용)
_cors_origins = [
    "http://localhost:8000",
    "http://127.0.0.1:8000",
    "https://mytube-ashy-seven.vercel.app",
]
if config.DEBUG:
    _cors_origins += ["http://localhost:3000", "http://127.0.0.1:3000"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization", "X-Requested-With"],
)

# [EXE] Ensure necessary directories exist
os.makedirs("uploads", exist_ok=True)


# [EXE] Ensure DB is initialized BEFORE accessing globals
try:
    db.ensure_local_db_migrated()
    db.migrate_db()
    print(f"[Main] Database migration checked: {db.get_db_path()}")
except Exception as e:
    print(f"[Main] Database initialization warning: {e}")

# 템플릿 및 정적 파일
templates = Jinja2Templates(directory=config.TEMPLATES_DIR)
templates.env.auto_reload = True
templates.env.cache = {}
templates.env.globals['app_version'] = config.APP_VERSION

# Static Files
app.mount("/static", StaticFiles(directory=config.STATIC_DIR), name="static")
# app.mount("/output", StaticFiles(directory=config.OUTPUT_DIR), name="output")
app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")
app.mount("/assets", StaticFiles(directory=config.ASSETS_DIR), name="assets")

# i18n
from services.i18n import Translator
app_lang = os.environ.get("APP_LANG", "ko")
translator = Translator(app_lang)

# Add t function to Jinja2 globals
templates.env.globals['t'] = translator.t
templates.env.globals['t_all'] = translator.t_all
templates.env.globals['current_lang'] = app_lang
templates.env.globals['window_lang'] = app_lang
templates.env.globals['app_mode'] = normalize_app_mode(db.get_global_setting("app_mode", DEFAULT_APP_MODE))
templates.env.globals['membership'] = auth_service.get_membership()
templates.env.globals['is_independent'] = auth_service.is_independent()
templates.env.globals['user_email'] = auth_service.get_user_email()
def get_license_key():
    if os.path.exists("license.key"):
        with open("license.key", "r") as f:
            return f.read().strip()
    return ""

def format_currency(value):
    try:
        return "{:,}".format(int(value))
    except (ValueError, TypeError):
        return value

templates.env.filters['format_currency'] = format_currency
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
        if saved and saved in ['ko', 'en', 'vi', 'th']:
            translator.set_lang(saved)
            app_lang = saved
            templates.env.globals['current_lang'] = app_lang
            templates.env.globals['window_lang'] = app_lang
            print(f"[I18N] Loaded language from DB: {app_lang}")
            return
    except Exception:
        pass
    # 2. 파일에서 읽기 (fallback)
    if os.path.exists(LANG_FILE):
        with open(LANG_FILE, "r") as f:
            saved_lang = f.read().strip()
            if saved_lang in ['ko', 'en', 'vi', 'th']:
                translator.set_lang(saved_lang)
                app_lang = saved_lang
                templates.env.globals['current_lang'] = app_lang
                templates.env.globals['window_lang'] = app_lang
                templates.env.globals['app_mode'] = normalize_app_mode(db.get_global_setting("app_mode", DEFAULT_APP_MODE))
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
from app.routers import youtube as youtube_router
from app.routers import tts as tts_router
from app.routers import repository as repository_router # [NEW]
from app.routers import health as health_router
from app.routers import queue as queue_router # [NEW]

from app.routers import audio as audio_router
from app.routers import music as music_router
from app.routers import sources as sources_router
from app.routers import pages as pages_router
from app.routers import gemini as gemini_router
from app.routers import image as image_router
from app.routers import thumbnails as thumbnails_router
from app.routers import templates as templates_router
from app.routers import auth as auth_router
from app.routers import update as update_router
from app.routers import learning as learning_router
from app.routers import admin_tenant as admin_tenant_router  # [NEW]
from app.routers import user_topics as user_topics_router  # [NEW]
from app.routers import referral as referral_router
from app.routers import support as support_router
from app.routers import announcements as announcements_router
from app.routers import director_api
from app.routers import admin_voices as admin_voices_router
from app.routers import voices as voices_router
from app.routers import script_api as script_api_router  # [AIR-0203]
from app.routers import director_api as director_api_router  # [AIR-0205]
from app.routers import production_api as production_api_router  # [AIR-0206]
from app.routers import prompt_package_api as prompt_package_api_router  # [AIR-0207]
from app.routers import asset_matching_api as asset_matching_api_router  # [AIR-0207]

app.include_router(update_router.router)
app.include_router(learning_router.router)
app.include_router(learning_router.admin_router)
app.include_router(autopilot_router.router)
app.include_router(video_router.router)
app.include_router(commerce_router.router)
app.include_router(projects_router.router)
app.include_router(channels_router.router)
app.include_router(media_router.router)
app.include_router(settings_router.router)
app.include_router(youtube_router.router)
app.include_router(tts_router.router)
app.include_router(repository_router.router)
app.include_router(health_router.router)
app.include_router(queue_router.router)
app.include_router(audio_router.router)
app.include_router(music_router.router)
app.include_router(sources_router.router)
app.include_router(pages_router.router)
app.include_router(gemini_router.router)
app.include_router(image_router.router)
app.include_router(thumbnails_router.router)
app.include_router(templates_router.router)
app.include_router(auth_router.router)
app.include_router(admin_tenant_router.router)  # [NEW]
app.include_router(user_topics_router.router)  # [NEW]
app.include_router(referral_router.router, prefix="/api")
app.include_router(support_router.router, prefix="/api")
app.include_router(announcements_router.router, prefix="/api")
app.include_router(admin_voices_router.router)
app.include_router(voices_router.router)
app.include_router(script_api_router.router, prefix="/api/script")  # [AIR-0203]
app.include_router(director_api_router.router, prefix="/api/director")  # [AIR-0205]
app.include_router(production_api_router.router, prefix="/api/production")  # [AIR-0206]
app.include_router(prompt_package_api_router.router, prefix="/api/packages")  # [AIR-0207]
app.include_router(asset_matching_api_router.router, prefix="/api/assets")  # [AIR-0207]
pages_router.init_pages(templates)
repository_router.init_repository(templates)  # [AIR-0134]


# output 폴더
os.makedirs(config.OUTPUT_DIR, exist_ok=True)
# app.mount("/output", StaticFiles(directory=config.OUTPUT_DIR), name="output")

# uploads 폴더 (인트로 등 업로드용)
os.makedirs("uploads", exist_ok=True)
app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")

@app.on_event("startup")
async def startup_event():
    """앱 시작 시 실행 (DB 초기화 및 마이그레이션)"""
    try:
        from config import Config

        # Load web-admin API keys first, then verify user-specific overrides.
        Config.load_remote_keys_from_supabase()
        auth_service.verify_license()

        db.ensure_local_db_migrated()
        db.init_db()
        db.migrate_db()
        db.reset_rendering_status() # [FIX] Stuck rendering status reset

        try:
            from services.project_sync_service import sync_dirty_projects
            from services.learning_sync_service import sync_learning_data
            asyncio.create_task(asyncio.to_thread(sync_dirty_projects, limit=20))
            asyncio.create_task(asyncio.to_thread(sync_learning_data, limit=100))
        except Exception as sync_e:
            print(f"[ProjectSync] Startup dirty sync warning: {sync_e}")

        # [NEW] Start Autopilot Batch Worker
        asyncio.create_task(autopilot_service.start_batch_worker())
        
        # [NEW] Start Referral Engagement Re-engagement Loop
        from app.services.referral_engagement_service import referral_engagement_service
        asyncio.create_task(referral_engagement_service.start_background_worker())

        # 키 로드 상태 출력
        from config import Config
        gemini_ok = "✅" if Config.GEMINI_API_KEY else "❌ 없음"
        youtube_ok = "✅" if Config.YOUTUBE_API_KEY else "❌ 없음"
        elevenlabs_ok = "✅" if Config.ELEVENLABS_API_KEY else "❌ 없음"
        print(f"[Startup] DB Initialized. Membership: {auth_service.get_membership()}")
        print(f"[Startup] API Keys — Gemini:{gemini_ok}  YouTube:{youtube_ok}  ElevenLabs:{elevenlabs_ok}")
        if not Config.GEMINI_API_KEY:
            print("[Startup] ⚠️  Gemini 키 없음 → mytube-ashy-seven.vercel.app 에서 키 저장 후 재시작 필요")
    except Exception as e:
        print(f"[Startup] Setup Failed: {e}")


# ===========================================
# Pydantic 모델
# ===========================================
from app.models.project import (
    ProjectSettingUpdate, ProjectSettingsSave,
    AnalysisSave, ScriptSave,
    MetadataSave, ShortsSave
)


# 스타일 매핑 
STYLE_PROMPTS = {
    "realistic": "A highly realistic photo, 8k resolution, highly detailed photography, lifelike textures, natural lighting, professional cinematography, high quality",
    "anime": "Anime style illustration, vibrant colors, detailed background, Makoto Shinkai style, high quality",
    "cinematic": "Cinematic movie shot, dramatic lighting, shadow and light depth, highly detailed, 4k",
    "minimal": "Minimalist flat vector illustration, simple shapes, clean lines, white background, high quality",
    "3d": "3D render, Pixar style, soft studio lighting, octane render, 4k, high quality",
    "k_webtoon": "Modern K-webtoon manhwa style, high-quality digital illustration, sharp line art, vibrant colors, expressive character, modern manhwa aesthetic, professional digital art, no text, no speech bubbles",
    "ghibli": "Studio Ghibli style, cel shaded, vibrant colors, lush background, Hayao Miyazaki style, highly detailed, masterfully painted",
    "k_manhwa": "A clean, high-quality, full-color webtoon style illustration in a 16:9 cinematic aspect ratio. Bold black outlines, flat graphic colors with soft gradients, clean vector-like finish. Isolated on a fully illustrated 16:9 detailed background. A cute, minimalist cartoon character with a perfectly uniform white circular head (solid white surface, no hair, shiny bald). THE FACE MUST HAVE a pair of distinct black eyes and a simple mouth. THE CHARACTER HAS EXACTLY TWO ARMS (one left arm, one right arm) AND EXACTLY TWO WHITE GLOVED HANDS TOTAL. NO THIRD ARM, NO FOURTH ARM, NO MULTIPLE LIMBS. NO REAR ARMS. The black limbs must have a perfectly uniform and consistent thickness. The character always wears a long-sleeved hooded sweatshirt (hoodie) that covers the arms down to the wrists, the hoodie is vibrant teal-blue (Brand Color: #00ADB5), black pants and simple sneakers. IMPORTANT: Background elements and other illustrated characters MUST NEVER overlap, touch, or be attached to the main character. The main character must be clearly separated from the background layers. ABSOLUTELY NO TEXT. NO HAIR. ONLY TWO ARMS AND TWO HANDS TOTAL. NO EXTRA LIMBS.",
    "philosophical": "Traditional oriental painting style, ink wash, philosophical atmosphere, historical documentary aesthetic.",
    "역사/동양철/다큐": "Traditional oriental painting style, ink wash, philosophical atmosphere, historical documentary aesthetic."
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
# API: 프로젝트 관리
# ===========================================

@app.post("/api/script/recommend-titles")
async def recommend_titles(
    keyword: str = Body(..., embed=True),
    topic: str = Body("", embed=True),
    language: str = Body("ko", embed=True)
):
    """키워드 기반 제목 추천"""
    titles = await gemini_service.generate_title_recommendations(
        keyword,
        topic,
        language,
        model=config.TITLE_GENERATION_MODEL,
    )
    return {"titles": titles}




@app.patch("/api/projects/{project_id}")
async def patch_project(project_id: int, background_tasks: BackgroundTasks, body: dict = Body(...)):
    """프로젝트 기본 정보 업데이트 (이름, 주제 등)"""
    try:
        allowed = {k: v for k, v in body.items() if k in ('name', 'topic', 'status')}
        if allowed:
            db.update_project(project_id, **allowed)
            _queue_project_sync(background_tasks, project_id)
        return {"status": "ok"}
    except Exception as e:
        raise HTTPException(500, str(e))


@app.post("/api/projects/{project_id}/script")
async def save_script(project_id: int, req: ScriptSave, background_tasks: BackgroundTasks):
    """대본 저장"""
    if req.language == "vi":
        db.update_project_setting(project_id, "script_vi", req.full_script)
    else:
        db.save_script(project_id, req.full_script, req.word_count, req.estimated_duration)
        db.update_project(project_id, status="scripted")
    try:
        from services import learning_service as _learning_service
        _learning_service.log_event(project_id, "human_edit", "script", {
            "language": req.language or "ko",
            "length": len(req.full_script or ""),
            "word_count": req.word_count,
            "estimated_duration": req.estimated_duration,
        }, source="user")
    except Exception:
        pass
    _queue_project_sync(background_tasks, project_id)
    return {"status": "ok"}

@app.get("/api/projects/{project_id}/script")
async def get_script(project_id: int):
    """대본 조회"""
    return db.get_script(project_id) or {}

class TranslateScriptRequest(BaseModel):
    target_language: str = "vi"

@app.post("/api/projects/{project_id}/translate-script")
async def translate_project_script(project_id: int, req: TranslateScriptRequest):
    """대본 번역 (베트남어/영어 + 발음기호)"""
    script_data = db.get_script(project_id)
    if not script_data or not script_data.get("full_script"):
        raise HTTPException(400, "Original script not found. Please generate it first.")
    
    original_script = script_data["full_script"]
    from services.gemini_service import gemini_service
    
    if req.target_language == "en":
        lang_prompt = "English"
        phonetic_instruction = "Additionally, beneath each translated line, provide the Romanized phonetic pronunciation of the ORIGINAL language script (e.g., Romaji for Japanese, Romaja for Korean) in square brackets."
        example_format = "4. Format: [Original Line] \\n [Phonetic Pronunciation] \\n [English Translation]"
    else:
        lang_prompt = "Vietnamese"
        phonetic_instruction = "do NOT provide any phonetic pronunciation."
        example_format = "4. Output ONLY the translated script text."

    prompt = (
        f"Translate the following video script into {lang_prompt}. {phonetic_instruction}\n\n"
        f"CRITICAL RULES:\n"
        f"1. Keep all speaker labels (e.g. '길동:', '철수:', 'Narrator:') exactly in their original form (do not translate names, but you can translate labels like 'Narrator:').\n"
        f"2. Keep all brackets containing emotion or direction tags in their original English form (e.g. keep '(excited)', '(whispering)', '(pause)' as is, do not translate them).\n"
        f"3. Keep the line-by-line structure, paragraphs, and blank lines exactly identical to the original.\n"
        f"{example_format}\n"
        f"5. Do not add any greeting, introductory text, explanations, or wrapping block quotes.\n\n"
        f"{original_script}"
    )
    
    try:
        translated_text = await gemini_service.generate_text(prompt, temperature=0.3)
        translated_text = translated_text.strip()
        
        # DB의 project_settings 테이블에 script_vi 필드로 동적 컬럼 저장
        db.update_project_setting(project_id, "script_vi", translated_text)
        
        return {
            "status": "success",
            "translated_script": translated_text
        }
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(500, f"Translation failed: {str(e)}")

@app.get("/api/projects/{project_id}/full")
async def get_project_full(project_id: int):
    """프로젝트 전체 데이터 조회 (Context Restoration용)"""
    try:
        project = db.get_project(project_id)
        if project and project.get("status") in ["remote_packaging", "remote_queued"]:
            from services.remote_drive_render_service import remote_drive_render_service
            remote_drive_render_service.sync_completed_result(project_id)
    except Exception as e:
        print(f"[RemoteDrive] Full data sync skipped: {e}")
    payload = db.get_project_full_data_v2(project_id) or {}
    if payload:
        from services.longform_asset_readiness import sync_project_asset_readiness
        payload["asset_readiness"] = sync_project_asset_readiness(project_id)
    return payload


@app.post("/api/projects/{project_id}/sync-topic-progress")
async def sync_project_topic_progress(project_id: int):
    try:
        synced = sync_topic_progress(project_id)
        return {"status": "ok", "synced": synced}
    except Exception as e:
        print(f"[Topic Progress Sync] {e}")
        return {"status": "error", "error": str(e)}


@app.post("/api/projects/{project_id}/analysis")
async def save_analysis(project_id: int, req: AnalysisSave, background_tasks: BackgroundTasks):
    """분석 결과 저장 및 백그라운드 학습 트리거"""
    try:
        db.save_analysis(project_id, req.video_data, req.analysis_result)
        
        # [NEW] 분석 성공 시 백그라운드에서 지식 추출 (학습 자동화)
        if req.analysis_result:
            v_id = req.video_data.get('id', '')
            if isinstance(v_id, dict): v_id = v_id.get('videoId', '')
            background_tasks.add_task(background_learn_strategy, v_id, req.analysis_result)
            
        return {"status": "ok"}
    except Exception as e:
        print(f"[Error] Save Analysis Failed: {e}")
        raise HTTPException(500, str(e))


@app.get("/api/projects/{project_id}/analysis")
async def get_analysis(project_id: int):
    """분석 결과 조회"""
    return db.get_analysis(project_id) or {}


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



@app.post("/api/projects/{project_id}/tts/upload")
async def save_external_tts(project_id: int, file: UploadFile = File(...)):
    """외부 TTS 오디오 파일 업로드 및 저장"""
    try:
        ext, _ = _validate_upload(file, _ALLOWED_AUDIO_EXT, _MAX_AUDIO_SIZE)
        # 1. 출력 경로 확보
        output_dir, web_dir = get_project_output_dir(project_id)

        # 2. 파일명 생성
        filename = f"tts_ext_{project_id}_{int(time.time())}{ext}"
        file_path = os.path.join(output_dir, filename)
        web_url = f"{web_dir}/{filename}"

        # 3. 저장 + 크기 검증
        content = await file.read()
        if len(content) > _MAX_AUDIO_SIZE:
            raise HTTPException(400, f"파일 크기가 너무 큽니다 (최대 {_MAX_AUDIO_SIZE//1024//1024}MB)")
        async with aiofiles.open(file_path, "wb") as f:
            await f.write(content)
            
        # 4. DB 업데이트 (TTS 결과로 등록)
        # save_tts(project_id, voice_id, voice_name, audio_path, duration)
        db.save_tts(project_id, "external_upload", "External Upload", file_path, 0.0)
        
        return {"status": "ok", "url": web_url, "path": file_path}
    except Exception as e:
        print(f"Error saving external TTS: {e}")
        return JSONResponse(status_code=500, content={"error": str(e)})


class AnimateRequest(BaseModel):
    scene_number: int
    prompt: str = "Cinematic slow motion, high quality"
    duration: float = 5.0
    method: str = "standard"

@app.post("/api/projects/{project_id}/scenes/animate")
async def animate_scene(project_id: int, req: AnimateRequest):
    """[REMOVED] Replicate(Wan) 기반 이미지->영상 변환은 더 이상 지원되지 않습니다."""
    return JSONResponse(status_code=501, content={"error": "이 영상 생성 방식은 더 이상 지원되지 않습니다."})

@app.post("/api/upload-video-to-project/{project_id}/{scene_number}")
async def upload_scene_video(project_id: int, scene_number: int, file: UploadFile = File(...)):
    """확장프로그램 혹은 수동 업로드를 통한 장면 미디어(비디오/이미지) 저장"""
    try:
        allowed = _ALLOWED_VIDEO_EXT | _ALLOWED_IMAGE_EXT
        ext, _ = _validate_upload(file, allowed, _MAX_VIDEO_SIZE)
        output_dir, web_dir = get_project_output_dir(project_id)

        is_image = ext.lower() in _ALLOWED_IMAGE_EXT
        prefix = "flow_img" if is_image else "flow_vid"
        max_size = _MAX_IMAGE_SIZE if is_image else _MAX_VIDEO_SIZE

        filename = f"{prefix}_p{project_id}_s{scene_number}_{int(time.time())}{ext}"
        file_path = os.path.join(output_dir, filename)
        web_url = f"{web_dir}/{filename}"

        content = await file.read()
        if len(content) > max_size:
            raise HTTPException(400, f"파일 크기가 너무 큽니다 (최대 {max_size//1024//1024}MB)")
        async with aiofiles.open(file_path, "wb") as f:
            await f.write(content)
            
        # DB 업데이트 (이미지/비디오 구분)
        if is_image:
            db.update_image_prompt_url(project_id, scene_number, web_url)
        else:
            db.update_image_prompt_video_url(project_id, scene_number, web_url)
        
        return {"status": "ok", "url": web_url, "path": file_path, "is_image": is_image}
    except Exception as e:
        print(f"Error saving scene media: {e}")
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
async def save_metadata(project_id: int, req: MetadataSave, app_mode: str = Query(None)):
    """메타데이터 저장 (app_mode별로 분리)"""
    app_mode = normalize_app_mode(app_mode)
    setting_key = f"metadata_{app_mode}"
    db.update_project_setting(
        project_id,
        setting_key,
        json.dumps({
            "titles": req.titles,
            "description": req.description,
            "tags": req.tags,
            "hashtags": req.hashtags,
        }, ensure_ascii=False)
    )
    return {"status": "ok"}

@app.get("/api/projects/{project_id}/metadata")
async def get_metadata(project_id: int, app_mode: str = Query(None)):
    """메타데이터 조회 (app_mode별로 분리)"""
    app_mode = normalize_app_mode(app_mode)
    return db.get_project_metadata(project_id, app_mode) or {}



# [REMOVED] Duplicate thumbnail save endpoint (Moved to line ~1630 with updated logic)

@app.post("/api/projects/{project_id}/intro/save")
async def save_intro_video(project_id: int, file: UploadFile = File(...)):
    """인트로(배경) 동영상 업로드 및 저장"""
    try:
        ext, _ = _validate_upload(file, _ALLOWED_VIDEO_EXT, _MAX_VIDEO_SIZE)
        # 1. 출력 경로 확보
        output_dir, web_dir = get_project_output_dir(project_id)

        # 2. 파일명 생성
        filename = f"intro_{project_id}_{int(time.time())}{ext}"
        file_path = os.path.join(output_dir, filename)
        web_url = f"{web_dir}/{filename}"

        # 3. 저장 + 크기 검증
        content = await file.read()
        if len(content) > _MAX_VIDEO_SIZE:
            raise HTTPException(400, f"파일 크기가 너무 큽니다 (최대 {_MAX_VIDEO_SIZE//1024//1024}MB)")
        async with aiofiles.open(file_path, "wb") as f:
            await f.write(content)
            
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


def _is_truthy_setting(value: Any) -> bool:
    return str(value).strip().lower() in ("1", "true", "yes", "on")


def _apply_longform_duration_lock(project_id: int, settings: Dict[str, Any]) -> Dict[str, Any]:
    current = db.get_project_settings(project_id) or {}
    app_mode = current.get("app_mode") or db.get_global_setting("app_mode", "longform")
    if app_mode != "longform" or not _is_truthy_setting(current.get("duration_locked")):
        return settings

    assigned_seconds = current.get("assigned_duration_seconds") or current.get("duration_seconds")
    if assigned_seconds:
        settings["duration_seconds"] = int(assigned_seconds)
    return settings


# AI가 배정한 스타일이 잠긴 프로젝트(style_locked=1)에서는 워커가 대본/이미지 스타일을
# 바꾸지 못하도록, 들어온 설정 dict에서 스타일 키를 현재 저장값으로 되돌린다.
_STYLE_LOCK_KEYS = ("script_style", "image_style", "visual_style")

def _apply_style_lock(project_id: int, settings: Dict[str, Any]) -> Dict[str, Any]:
    if not any(k in settings for k in _STYLE_LOCK_KEYS):
        return settings
    current = db.get_project_settings(project_id) or {}
    if not _is_truthy_setting(current.get("style_locked")):
        return settings
    for key in _STYLE_LOCK_KEYS:
        if key in settings:
            saved = current.get(key)
            if saved is not None:
                settings[key] = saved
            else:
                settings.pop(key, None)
    return settings

def _is_style_locked(project_id: int) -> bool:
    current = db.get_project_settings(project_id) or {}
    return _is_truthy_setting(current.get("style_locked"))

@app.post("/api/projects/{project_id}/settings")
async def save_project_settings(project_id: int, req: ProjectSettingsSave):
    """프로젝트 핵심 설정 저장"""
    try:
        settings = {k: v for k, v in req.dict().items() if v is not None}
        settings = _apply_longform_duration_lock(project_id, settings)
        settings = _apply_style_lock(project_id, settings)
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
async def get_project_settings_route(project_id: int):
    """프로젝트 핵심 설정 조회"""
    try:
        settings = db.get_project_settings(project_id)
        return settings or {}
    except Exception as e:
        print(f"❌ [API] get_project_settings Error: {e}")
        # 만약 테이블이 없는 에러라면 (OperationalError), DB 초기화 시도
        if "no such table" in str(e).lower():
            print("🔄 [API] Table missing. Attempting lazy DB initialization...")
            try:
                db.init_db()
                return db.get_project_settings(project_id) or {}
            except Exception as e2:
                print(f"❌ [API] Lazy initialization failed: {e2}")
        return {"status": "error", "error": str(e)}

@app.patch("/api/projects/{project_id}/settings/{key}")
async def update_project_setting(project_id: int, key: str, value: str):
    """단일 설정 업데이트"""
    # 숫자 변환
    if key in ['duration_seconds', 'is_uploaded', 'subtitle_bg_enabled', 'subtitle_stroke_enabled']:
        value = int(value)
    elif key in ['subtitle_font_size', 'subtitle_stroke_width', 'subtitle_line_spacing', 'subtitle_bg_opacity']:
        value = float(value)

    if key == 'duration_seconds':
        value = _apply_longform_duration_lock(project_id, {'duration_seconds': value})['duration_seconds']

    # AI가 배정한 스타일이 잠긴 경우 스타일 키 변경을 무시한다.
    if key in _STYLE_LOCK_KEYS and _is_style_locked(project_id):
        return {"status": "locked", "message": "AI가 배정한 스타일은 변경할 수 없습니다.", "key": key}

    result = db.update_project_setting(project_id, key, value)
    
    # [FIX] Sync to Global Settings (Project 1)
    if project_id != 1 and key in SYNC_KEYS:
        db.update_project_setting(1, key, value)
        print(f"🔄 Synced '{key}' to Global (Project 1)")

    if not result:
        raise HTTPException(400, f"유효하지 않은 설정 키: {key}")
    return {"status": "ok"}



# ===========================================
# API: 상태 확인
# ===========================================



@app.get("/api/utils/phonetic")
def get_phonetic(text: str = "", target_lang: str = "en"):
    """Generate phonetic romanization/romaji for given text."""
    if not text:
        return {"phonetic": ""}
    
    try:
        result = kakasi.convert(text)
        romaji = " ".join([item['hepburn'] for item in result])
        return {"phonetic": romaji.strip()}
    except Exception as e:
        print("Kakasi error:", e)
        return {"phonetic": text}


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





# [REMOVED] Duplicate API key routes (Consolidated at line 960)


# [REMOVED] Duplicate API key routes (Consolidated at line 960)

# [REMOVED] Duplicate project settings routes (Consolidated at lines 769, 793)





# ===========================================
# API: 자막 (Subtitle)
# ===========================================








# [NEW] Reset Timeline to Latest Generated State



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
    model = request.get("model", "veo-3.1-fast-generate-preview")
    
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

        # 데이터베이스에 경로 저장
        conn = database.get_db()
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE project_settings 
            SET intro_video_path = ?, background_video_url = ?, updated_at = CURRENT_TIMESTAMP
            WHERE project_id = ?
        """, (str(intro_path), web_url, project_id))
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
            SET intro_video_path = NULL, background_video_url = NULL, updated_at = CURRENT_TIMESTAMP
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














class AutoPilotStartRequest(BaseModel):
    keyword: Optional[str] = None
    topic: Optional[str] = None
    mode: str = "longform"
    image_style: str = "realistic"
    visual_style: str = "realistic"
    thumbnail_style: Optional[str] = "face"
    video_scene_count: Optional[int] = 0
    all_video: Optional[bool] = False
    video_engine: Optional[str] = "veo"
    motion_method: Optional[str] = "standard"
    char_ethnicity: Optional[str] = None
    narrative_style: str = "informative"
    script_style: Optional[str] = None
    voice_id: str = "ko-KR-Neural2-A"
    voice_provider: Optional[str] = None
    subtitle_style: str = "Basic_White"
    duration_seconds: Optional[int] = 0
    duration_minutes: Optional[int] = None
    subtitle_settings: Optional[Dict[str, Any]] = None
    preset_id: Optional[int] = None
    upload_privacy: Optional[str] = "private"
    upload_schedule_at: Optional[str] = None
    youtube_channel_id: Optional[int] = None
    creation_mode: str = "default"
    product_url: Optional[str] = None
    use_character_analysis: bool = False
    is_queued: bool = False
    aspect_ratio: Optional[str] = "16:9"
    longform_music: Optional[Dict[str, Any]] = None





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
        lambda: asyncio.run(autopilot_service.run_project_workflow(keyword)),
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
    background_tasks.add_task(autopilot_service.run_project_workflow, keyword)
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

    background_tasks.add_task(autopilot_service.run_project_workflow, project['topic'], project_id, config_dict)
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

@app.post("/api/project/{project_id}/render-queue")
async def add_to_render_queue(project_id: int):
    """렌더링 대기열에 추가 — 상태를 tts_done으로 설정"""
    try:
        db.update_project(project_id, status="tts_done")
        return {"status": "ok", "message": "렌더링 대기열에 추가되었습니다"}
    except Exception as e:
        raise HTTPException(500, str(e))

@app.get("/api/render-queue")
async def get_render_queue():
    """Return local render queue plus remote Google Drive render queue."""
    try:
        all_projects = db.get_all_projects()
        queue = []

        for p in all_projects:
            if p.get("status") != "tts_done":
                continue
            pid = p["id"]
            settings = db.get_project_settings(pid) or {}
            item = dict(p)
            item["app_mode"] = settings.get("app_mode", "longform")
            script = db.get_script(pid)
            if script and script.get("title"):
                item["display_name"] = script["title"]
            elif settings.get("title"):
                item["display_name"] = settings["title"]
            else:
                item["display_name"] = item.get("name") or item.get("topic") or f"Project {pid}"
            try:
                prompts = db.get_image_prompts(pid) or []
                scene_count = len(prompts)
            except Exception:
                scene_count = 0
            item["scene_count"] = scene_count
            est_sec = max(60, scene_count * 3 + 30)
            if est_sec < 3600:
                item["est_time"] = f"약 {est_sec // 60}분"
            else:
                item["est_time"] = f"약 {est_sec // 3600}시간 {(est_sec % 3600) // 60}분"
            item["queue_source"] = "local"
            queue.append(item)

        try:
            from services.remote_drive_render_service import remote_drive_render_service

            remote_rows = remote_drive_render_service.list_queue_rows(
                statuses=["pending", "rendering", "completed", "failed"],
                limit=100,
            )
            for row in remote_rows:
                metadata = row.get("metadata") or {}
                if isinstance(metadata, str):
                    try:
                        metadata = json.loads(metadata)
                    except Exception:
                        metadata = {}
                queue.append({
                    "id": row.get("project_id") or row.get("id"),
                    "project_id": row.get("project_id"),
                    "task_id": row.get("id"),
                    "name": row.get("project_name"),
                    "display_name": metadata.get("playlist_title") or row.get("project_name") or f"Project {row.get('project_id')}",
                    "topic": metadata.get("playlist_title") or row.get("project_name") or "",
                    "status": row.get("status"),
                    "app_mode": metadata.get("app_mode") or metadata.get("display_type") or "longform",
                    "render_style": metadata.get("render_style"),
                    "queue_type": metadata.get("queue_type"),
                    "queue_source": "remote_drive",
                    "remote_queue": True,
                    "remote_progress": row.get("progress"),
                    "remote_message": row.get("message"),
                    "track_count": metadata.get("track_count"),
                    "updated_at": row.get("updated_at"),
                    "admin_action_required": metadata.get("admin_action_required"),
                })
        except Exception as remote_err:
            print(f"[Queue] Failed to load remote render queue: {remote_err}")

        queue.sort(key=lambda x: (0 if x.get("queue_source") == "remote_drive" else 1, x.get("id") or 0))
        return {"status": "ok", "queue": queue}
    except Exception as e:
        raise HTTPException(500, str(e))
# ===========================================


# ===========================================
# 서버 실행 (Direct Run)
# ===========================================

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












@app.get("/api/projects/{project_id}/drive-bundle")
async def get_drive_bundle(project_id: int):
    try:
        bundle = drive_bundle_service.get_project_bundle(project_id)
        return {
            "status": "ok",
            "bundle": {
                "folder": bundle.get("folder"),
                "video_file": bundle.get("video_file"),
                "thumbnail_file": bundle.get("thumbnail_file"),
                "metadata_file": bundle.get("metadata_file"),
                "metadata_json": bundle.get("metadata_json"),
                "title": bundle.get("title"),
                "description": bundle.get("description"),
                "tags": bundle.get("tags"),
                "hashtags": bundle.get("hashtags"),
                "available": bool((bundle.get("video_file") or {}).get("id")),
            },
        }
    except Exception as e:
        print(f"[DriveBundle] Summary error: {e}")
        return {"status": "error", "error": str(e)}














if __name__ == "__main__":
    print("=" * 50)
    print("PICADILLY STUDIO v2.0")
    print("-" * 50)

    config.validate()
    
    # Initialize & Migrate Database
    db.init_db()
    db.migrate_db()
    
    # [NEW] Verify License & Membership
    from services.auth_service import auth_service
    if not auth_service.verify_license():
        print("!" * 50)
        print("라이선스 인증에 실패했습니다.")
        if auth_service.is_restricted():
            print("관리자에 의해 계정 사용이 중단되었습니다.")
        print("!" * 50)
        # In actual EXE we might want to exit, but for now we let it run
    
    # [NEW] Start Real-time Admin Monitoring (Check every 10m)
    auth_service.start_monitoring()
    
    # [NEW] Auto Publish Service Start
    from services.auto_publish_service import auto_publish_service
    auto_publish_service.start()

    # [SDK] Smart Queue Dispatcher: disabled by default (web-admin owns topic generation)
    if os.getenv("ENABLE_USER_APP_DISPATCHER", "false").strip().lower() == "true":
        from services.dispatcher_service import dispatcher_service
        dispatcher_service.start()
        print("[Dispatcher] User App Dispatcher started (ENABLE_USER_APP_DISPATCHER=true)")
    else:
        print("[Dispatcher] Skipped (ENABLE_USER_APP_DISPATCHER not set). Web-admin handles topic dispatch.")

    print(f"[*] 서버 시간(KST): {config.get_kst_time().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"[*] 서버 주소: http://{config.HOST}:{config.PORT}")
    print("=" * 50)

    is_frozen = getattr(sys, "frozen", False)
    enable_reload = bool(config.DEBUG and not is_frozen)

    def _wait_for_server(host: str, port: int, timeout: float = 30.0) -> bool:
        """Poll until the local server is actually accepting TCP connections,
        instead of guessing with a fixed sleep. Startup time varies a lot on
        real end-user machines (cold disk cache, antivirus scanning a fresh
        install, etc.) — opening a browser/webview before the server is
        actually listening produces a connection-refused page instead of
        the app, which is exactly what a fixed short sleep risks."""
        import socket
        import time as _time
        deadline = _time.time() + timeout
        while _time.time() < deadline:
            try:
                with socket.create_connection((host, port), timeout=0.5):
                    return True
            except OSError:
                _time.sleep(0.3)
        return False

    # 1. 개발/디버그 핫리로딩 모드: uvicorn 메인 루프 실행 및 일반 브라우저 자동 오픈
    if enable_reload:
        import webbrowser
        import threading
        import time

        def open_browser():
            _wait_for_server(config.HOST, config.PORT)
            webbrowser.open(f"http://{config.HOST}:{config.PORT}")

        print("개발 모드: 브라우저 자동 실행 대기 중...")
        threading.Thread(target=open_browser, daemon=True).start()

        uvicorn.run(
            "main:app",
            host=config.HOST,
            port=config.PORT,
            reload=True,
            log_level="info"
        )
    # 2. 설치본(frozen) 혹은 프로덕션 모드: pywebview를 사용해 독립 데스크톱 창으로 구동
    else:
        import threading
        import time
        
        def _log_startup_event(message: str) -> None:
            # console=False 빌드는 stdout이 보이지 않으므로, 백그라운드 서버
            # 스레드가 조용히 죽는 경우를 진단하려면 파일 로그가 유일한 단서.
            # main.py의 기존 DEBUG_LOG_PATH 관례를 재사용.
            print(message)
            try:
                import datetime as _dt
                with open(config.DEBUG_LOG_PATH, "a", encoding="utf-8") as rf:
                    rf.write(f"[{_dt.datetime.now()}] [startup] {message}\n")
            except Exception:
                pass

        # 백그라운드 스레드에서 uvicorn 서버 실행. uvicorn.run()이 예외를
        # 던지면 daemon 스레드가 조용히 죽고 아무 표시도 없이 서버가
        # 응답하지 않는 상태가 된다 — 반드시 잡아서 로그 파일에 남긴다.
        def run_server():
            _log_startup_event(f"server thread starting on {config.HOST}:{config.PORT}")
            try:
                uvicorn.run(
                    app,
                    host=config.HOST,
                    port=config.PORT,
                    reload=False,
                    log_level="info",
                    log_config=None
                )
                _log_startup_event("uvicorn.run() returned normally (server stopped)")
            except Exception as server_error:
                import traceback
                _log_startup_event(f"CRITICAL: server thread crashed: {server_error}\n{traceback.format_exc()}")

        server_thread = threading.Thread(target=run_server, daemon=True)
        server_thread.start()

        print("프로덕션 모드: 서버 준비 대기 중...")
        if not _wait_for_server(config.HOST, config.PORT):
            _log_startup_event(
                f"WARNING: server did not become reachable within the wait timeout "
                f"(host={config.HOST}, port={config.PORT}); the background thread may "
                "have crashed during startup — check the lines above for a traceback."
            )

        print("프로덕션 모드: 독립 데스크톱 창(webview) 실행 중...")

        try:
            import webview

            # 독립 데스크톱 창 생성. pywebview on Windows only has one native
            # backend candidate (winforms, via pythonnet/.NET interop — see
            # webview/guilib.py); there is no pure-Python fallback it can try
            # instead. Whether that interop actually works depends on the
            # target machine's installed .NET Framework/Core state, which
            # varies across real end-user PCs and isn't something a frozen
            # build can guarantee. If it fails for any reason, fall through
            # to opening the default browser (below) rather than crashing —
            # the app must still be usable even without the native window
            # chrome.
            _ico = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static", "img", "air_studio.ico")
            webview.create_window(
                "AIR Studio",
                f"http://{config.HOST}:{config.PORT}",
                width=1280,
                height=800,
                resizable=True
            )
            webview.start(icon=_ico if os.path.exists(_ico) else None)
        except Exception as webview_error:
            _log_startup_event(f"webview(독립 창) 초기화 실패, 기본 브라우저로 실행합니다: {webview_error}")
            import webbrowser

            # Server readiness was already confirmed above (before webview was
            # even attempted), so no additional wait is needed here — just open.
            webbrowser.open(f"http://{config.HOST}:{config.PORT}")

            # server_thread (started above) is already bound to config.HOST:PORT —
            # do NOT call uvicorn.run() again here, it would try to bind the same
            # port a second time and crash with "address already in use". Just
            # keep the main thread alive on the already-running server instead.
            server_thread.join()

