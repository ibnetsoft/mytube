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
import aiofiles
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


# FastAPI 앱 생성
app = FastAPI(
    title="피카디리스튜디오",
    description="AI 기반 YouTube 영상 자동화 제작 플랫폼",
    version="2.0.0"
)

# CORS 설정 (로컬 앱 전용)
_cors_origins = [
    "http://localhost:8000",
    "http://127.0.0.1:8000",
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
    db.migrate_db()
    print("[Main] Database migration checked.")
except Exception as e:
    print(f"[Main] Database initialization warning: {e}")

# 템플릿 및 정적 파일
templates = Jinja2Templates(directory=config.TEMPLATES_DIR)

# Static Files
app.mount("/static", StaticFiles(directory=config.STATIC_DIR), name="static")
app.mount("/output", StaticFiles(directory=config.OUTPUT_DIR), name="output")
app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")

# i18n
from services.i18n import Translator
app_lang = os.environ.get("APP_LANG", "ko")
translator = Translator(app_lang)

# Add t function to Jinja2 globals
templates.env.globals['t'] = translator.t
templates.env.globals['current_lang'] = app_lang
templates.env.globals['app_mode'] = db.get_global_setting("app_mode", "longform")
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
                templates.env.globals['app_mode'] = db.get_global_setting("app_mode", "longform")
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

from app.routers import audio as audio_router
from app.routers import sources as sources_router
from app.routers import pages as pages_router
from app.routers import gemini as gemini_router
from app.routers import image as image_router

app.include_router(autopilot_router.router)
app.include_router(video_router.router)
app.include_router(commerce_router.router)
app.include_router(projects_router.router)
app.include_router(channels_router.router)
app.include_router(media_router.router)
app.include_router(settings_router.router)
app.include_router(repository_router.router)
app.include_router(queue_router.router)
app.include_router(audio_router.router)
app.include_router(sources_router.router)
app.include_router(pages_router.router)
app.include_router(gemini_router.router)
app.include_router(image_router.router)
pages_router.init_pages(templates)


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
# API: 프로젝트 관리
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
             except Exception:
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
                
                async with aiofiles.open(output_path, "wb") as f:
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

@app.post("/api/projects/{project_id}/image-prompts")
async def save_image_prompts(project_id: int, req: ImagePromptsSave):
    """이미지 프롬프트 저장"""
    db.save_image_prompts(project_id, req.prompts)
    return {"status": "ok"}

@app.get("/api/projects/{project_id}/image-prompts")
async def get_image_prompts(project_id: int):
    """이미지 프롬프트 조회"""
    return {"status": "ok", "prompts": db.get_image_prompts(project_id)}

class BulkPromptUpdate(BaseModel):
    texts: str

@app.post("/api/projects/{project_id}/bulk-update-prompts")
async def bulk_update_prompts(project_id: int, req: BulkPromptUpdate):
    """프롬프트 일괄 업데이트 (텍스트 목록 기반)"""
    try:
        # 1. 텍스트 분리 (빈 줄 제외)
        lines = [line.strip() for line in req.texts.split('\n') if line.strip()]
        if not lines:
            raise HTTPException(400, "입력된 프롬프트가 없습니다.")

        # 2. 기존 프롬프트 조회
        existing = db.get_image_prompts(project_id)
        
        new_prompts = []
        for i, line in enumerate(lines):
            scene_number = i + 1
            # 기존 데이터가 있으면 필드 유지, 아니면 신규 생성
            base = next((p for p in existing if p['scene_number'] == scene_number), {})
            
            prompt_item = {
                "scene_number": scene_number,
                "scene_text": base.get("scene_text") or f"Scene {scene_number}",
                "prompt_ko": line,                     # 프롬프트 내용을 KO/EN 모두에 일단 넣음 (사용자 편의)
                "prompt_en": line, 
                "image_url": base.get("image_url", ""),
                "video_url": base.get("video_url", ""),
                "engine": base.get("engine", "wan"),
                "scene_type": base.get("scene_type", ""),
                "motion_desc": base.get("motion_desc", "")
            }
            new_prompts.append(prompt_item)
            
        # 3. DB 저장
        db.save_image_prompts(project_id, new_prompts)
        
        return {"status": "success", "count": len(new_prompts)}
    except Exception as e:
        print(f"Bulk Update Error: {e}")
        raise HTTPException(500, str(e))


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
        async with aiofiles.open(output_path, "wb") as f:
            await f.write(video_bytes)

        video_web_url = f"{web_dir}/{filename}"
        db.update_image_prompt_video_url(project_id, req.scene_number, video_web_url)
        return {"status": "success", "video_url": video_web_url}

    except Exception as e:
        print(f"Animate Error: {e}")
        return JSONResponse(status_code=500, content={"error": str(e)})

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
    """서버 상태 및 API 연결 확인"""
    return {
        "status": "ok",
        "version": "2.0.0",
        "apis": {
            "youtube": bool(config.YOUTUBE_API_KEY),
            "gemini": bool(config.GEMINI_API_KEY),
            "elevenlabs": bool(config.ELEVENLABS_API_KEY),
            "replicate": bool(config.REPLICATE_API_TOKEN),
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
    topview_uid: Optional[str] = None
    akool_id: Optional[str] = None
    akool_secret: Optional[str] = None
    akool_api_key: Optional[str] = None
    blog_client_id: Optional[str] = None
    blog_client_secret: Optional[str] = None
    blog_id: Optional[str] = None
    wp_url: Optional[str] = None
    wp_username: Optional[str] = None
    wp_password: Optional[str] = None

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
        'topview_uid': 'TOPVIEW_UID',
        'akool_id': 'AKOOL_CLIENT_ID',
        'akool_secret': 'AKOOL_CLIENT_SECRET',
        'akool_api_key': 'AKOOL_API_KEY',
        'blog_client_id': 'BLOG_CLIENT_ID',
        'blog_client_secret': 'BLOG_CLIENT_SECRET',
        'blog_id': 'BLOG_ID',
        'wp_url': 'WP_URL',
        'wp_username': 'WP_USERNAME',
        'wp_password': 'WP_PASSWORD'
    }

    req_dict = req.dict()
    print(f"[API_KEY] Save request received. Fields present: {[k for k,v in req_dict.items() if v is not None]}")
    for field, config_key in mapping.items():
        val = req_dict.get(field)
        if val is not None and val.strip():
            print(f"[API_KEY] Updating {field} -> {config_key} (len: {len(val.strip())})")
            config.update_api_key(config_key, val.strip())
            updated.append(field)

    return {
        "status": "ok",
        "updated": updated,
        "message": f"{len(updated)}개의 API 키가 저장되었습니다"
    }


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
        data = response.json()
        
        # [NEW] Error Handling for API Credentials
        if response.status_code != 200:
            error_data = data.get("error", {})
            message = error_data.get("message", "YouTube API Error")
            print(f"[YouTube Search] Failed: {response.status_code} - {message}")
            if "API key not valid" in message or "API_KEY_INVALID" in str(error_data):
                return {"error": "API_KEY_INVALID", "message": "유효하지 않은 YouTube API 키입니다. 설정에서 확인해주세요."}
            return {"error": "API_ERROR", "message": message}

        return data

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
        data = response.json()
        if response.status_code != 200:
            error_data = data.get("error", {})
            message = error_data.get("message", "YouTube API Error")
            print(f"[YouTube Video] Failed: {response.status_code} - {message}")
            return {"error": "API_ERROR", "message": message}
        return data


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
                         except Exception: pass
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
                             except Exception: pass
                         except Exception as e:
                             print(f"pydub check failed: {e}")
                             # Fallback to MoviePy
                             try:
                                 from moviepy import AudioFileClip
                                 with AudioFileClip(output_path) as ac:
                                     duration = ac.duration
                             except Exception: pass
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
        ext, _ = _validate_upload(file, _ALLOWED_IMAGE_EXT, _MAX_IMAGE_SIZE)
        # public/templates 폴더
        template_dir = os.path.join(config.STATIC_DIR, "templates")
        os.makedirs(template_dir, exist_ok=True)

        filename = f"template_{int(time.time())}{ext}"
        filepath = os.path.join(template_dir, filename)

        content = await file.read()
        if len(content) > _MAX_IMAGE_SIZE:
            raise HTTPException(400, f"파일 크기가 너무 큽니다 (최대 {_MAX_IMAGE_SIZE//1024//1024}MB)")
        async with aiofiles.open(filepath, "wb") as f:
            await f.write(content)
            
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


# [REMOVED] Duplicate API key routes (Consolidated at line 960)

# [REMOVED] Duplicate project settings routes (Consolidated at lines 769, 793)

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
    except Exception:
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
        except Exception:
            pass

    return {"voices": voices}


# ===========================================
# API: 자막 (Subtitle)
# ===========================================








# [NEW] Reset Timeline to Latest Generated State



class ThumbnailTextRequest(BaseModel):
    """AI 썸네일 문구 생성 요청"""
    project_id: int
    thumbnail_style: str = "face"
    target_language: str = "ko"


@app.post("/api/settings/thumbnail-style-sample/{style_key}")
async def upload_thumbnail_style_sample(style_key: str, file: UploadFile = File(...)):
    """썸네일 스타일 샘플 이미지 업로드"""
    try:
        ext, _ = _validate_upload(file, _ALLOWED_IMAGE_EXT, _MAX_IMAGE_SIZE)
        save_dir = "static/thumbnail_samples"
        os.makedirs(save_dir, exist_ok=True)

        filename = f"{style_key}{ext}"
        filepath = os.path.join(save_dir, filename)

        # 기존 다른 확장자 파일 삭제 (중복 방지)
        for old_f in os.listdir(save_dir):
            if old_f.startswith(f"{style_key}."):
                try:
                    os.remove(os.path.join(save_dir, old_f))
                except Exception:
                    pass

        content = await file.read()
        if len(content) > _MAX_IMAGE_SIZE:
            raise HTTPException(400, f"파일 크기가 너무 큽니다 (최대 {_MAX_IMAGE_SIZE//1024//1024}MB)")
        async with aiofiles.open(filepath, "wb") as f:
            await f.write(content)
            
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
                    except Exception: pass
        
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


@app.post("/api/projects/{project_id}/thumbnail/save")
async def save_project_thumbnail(project_id: int, file: UploadFile = File(...)):
    """최종 썸네일(합성본) 저장"""
    try:
        ext, _ = _validate_upload(file, _ALLOWED_IMAGE_EXT, _MAX_IMAGE_SIZE)
        save_dir = os.path.join(config.OUTPUT_DIR, "thumbnails")
        os.makedirs(save_dir, exist_ok=True)

        filename = f"thumbnail_{project_id}_{int(time.time())}{ext}"
        filepath = os.path.join(save_dir, filename)

        content = await file.read()
        if len(content) == 0:
            raise HTTPException(400, "빈 파일입니다.")
        if len(content) > _MAX_IMAGE_SIZE:
            raise HTTPException(400, f"파일 크기가 너무 큽니다 (최대 {_MAX_IMAGE_SIZE//1024//1024}MB)")

        async with aiofiles.open(filepath, "wb") as f:
            await f.write(content)
            
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
        except Exception:
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



class AutoPilotStartRequest(BaseModel):
    keyword: Optional[str] = None
    topic: Optional[str] = None
    mode: str = "longform"
    image_style: str = "realistic"
    visual_style: str = "realistic"
    thumbnail_style: Optional[str] = "face"
    video_scene_count: Optional[int] = 0
    all_video: Optional[bool] = False
    video_engine: Optional[str] = "wan"
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
        except Exception:
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
             except Exception: pass

    # 2. Topic Resolve
    topic = req.topic or req.keyword
    if not topic:
         return {"status": "error", "error": "Topic (or keyword) is required"}

    # 3. Start Workflow in Background
    config_dict = {
        "mode": req.mode,
        "image_style": req.image_style or req.visual_style,
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
        "subtitle_settings": req.subtitle_settings,
        "use_character_analysis": req.use_character_analysis,
        "upload_privacy": req.upload_privacy,
    }
    
    # Create Project First
    project_name = f"[Auto] {topic}"
    project_id = db.create_project(name=project_name, topic=topic, app_mode=req.mode)
    
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
    if req.video_engine:
         db.update_project_setting(project_id, "video_engine", req.video_engine)
    if req.mode:
         db.update_project_setting(project_id, "app_mode", req.mode)
    
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
    """렌더링 대기 중인 프로젝트 목록 (status=tts_done)"""
    try:
        all_projects = db.get_all_projects()
        queue = []
        for p in all_projects:
            if p.get("status") == "tts_done":
                pid = p["id"]
                settings = db.get_project_settings(pid) or {}
                p["app_mode"] = settings.get("app_mode", "longform")
                # 프로젝트 표시명: script title > settings title > project name > topic
                script = db.get_script(pid)
                if script and script.get("title"):
                    p["display_name"] = script["title"]
                elif settings.get("title"):
                    p["display_name"] = settings["title"]
                else:
                    p["display_name"] = p.get("name") or p.get("topic") or f"프로젝트 {pid}"
                # 씬 수로 예상 렌더링 시간 추정
                try:
                    prompts = db.get_image_prompts(pid) or []
                    scene_count = len(prompts)
                except Exception:
                    scene_count = 0
                p["scene_count"] = scene_count
                est_sec = max(60, scene_count * 3 + 30)
                if est_sec < 3600:
                    p["est_time"] = f"약 {est_sec // 60}분"
                else:
                    p["est_time"] = f"약 {est_sec // 3600}시간 {(est_sec % 3600) // 60}분"
                queue.append(p)
        queue.sort(key=lambda x: x.get("id", 0))
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
    except Exception:
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

