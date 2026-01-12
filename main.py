"""
wingsAIStudio - FastAPI 메인 서버
YouTube 영상 자동화 제작 플랫폼 (Python 기반)
"""
from fastapi import FastAPI, HTTPException, BackgroundTasks, Query, Body, Request, Form, UploadFile, File
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional, Dict, Any, Union
import uvicorn
import os
import httpx
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
from services.gemini_service import gemini_service

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
app.mount("/static", StaticFiles(directory=config.STATIC_DIR), name="static")

# output 폴더
os.makedirs(config.OUTPUT_DIR, exist_ok=True)
app.mount("/output", StaticFiles(directory=config.OUTPUT_DIR), name="output")

@app.on_event("startup")
async def startup_event():
    """앱 시작 시 실행 (DB 초기화 및 마이그레이션)"""
    try:
        db.init_db()
        db.migrate_db()
        print("[Startup] DB Initialized & Migrated")
    except Exception as e:
        print(f"[Startup] DB Setup Failed: {e}")


# ===========================================
# Pydantic 모델
# ===========================================

class SearchRequest(BaseModel):
    query: str
    max_results: int = 10
    order: str = "relevance"
    published_after: Optional[str] = None
    video_duration: str = "short"  # any, long, medium, short (기본값: short)
    relevance_language: Optional[str] = None # ko, en, ja, etc.

class GeminiRequest(BaseModel):
    prompt: str
    temperature: float = 0.7
    max_tokens: int = 8192

class TTSRequest(BaseModel):
    text: str
    voice_id: Optional[str] = None
    provider: str = "elevenlabs"  # elevenlabs, google_cloud, gtts, gemini
    project_id: Optional[int] = None
    language: Optional[str] = "ko-KR"
    style_prompt: Optional[str] = None  # for gemini
    speed: Optional[float] = 1.0  # 0.5 ~ 2.0
    multi_voice: bool = False
    voice_map: Optional[Dict[str, str]] = {}  # { "철수": "voice_id_1" }

class VideoRequest(BaseModel):
    script: str
    image_prompts: List[str]
    voice_id: Optional[str] = None
    style: str = "default"

class ProjectCreate(BaseModel):
    name: str
    topic: Optional[str] = None
    target_language: Optional[str] = "ko"

class ProjectUpdate(BaseModel):
    name: Optional[str] = None
    topic: Optional[str] = None
    status: Optional[str] = None

class AnalysisSave(BaseModel):
    video_data: dict
    analysis_result: dict

class ScriptStructureSave(BaseModel):
    hook: str
    sections: List[dict]
    cta: str
    style: str
    duration: int

class ScriptSave(BaseModel):
    full_script: str
    word_count: int
    estimated_duration: int

class ImagePromptsSave(BaseModel):
    prompts: List[dict]

class MetadataSave(BaseModel):
    titles: List[str]
    description: str
    tags: List[str]
    hashtags: List[str]

class PromptsGenerateRequest(BaseModel):
    script: str
    style: str = "realistic"
    count: int = 0

class ThumbnailsSave(BaseModel):
    ideas: List[dict]
    texts: List[str]

class ShortsSave(BaseModel):
    shorts_data: List[dict]

class ProjectSettingsSave(BaseModel):
    title: Optional[str] = None
    thumbnail_text: Optional[str] = None
    thumbnail_url: Optional[str] = None
    duration_seconds: Optional[int] = None
    aspect_ratio: Optional[str] = None
    script: Optional[str] = None
    hashtags: Optional[str] = None
    voice_tone: Optional[str] = None
    video_command: Optional[str] = None
    video_path: Optional[str] = None
    is_uploaded: Optional[int] = None
    subtitle_style_enum: Optional[str] = None
class ChannelCreate(BaseModel):
    name: str
    handle: str
    description: Optional[str] = None

class ChannelResponse(BaseModel):
    id: int
    name: str
    handle: str
    description: Optional[str]
    created_at: Any

    subtitle_stroke_width: Optional[float] = None
    subtitle_position_y: Optional[int] = None
    background_video_url: Optional[str] = None # 루프 동영상 배경 URL

class SubtitleDefaultSave(BaseModel):
    subtitle_font: str
    subtitle_font_size: int
    subtitle_color: str
    subtitle_style_enum: str
    subtitle_stroke_color: str
    subtitle_stroke_width: float


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
        "title": "영상 업로드"
    })

@app.get("/subtitle_gen", response_class=HTMLResponse)
async def page_subtitle_gen(request: Request):
    """자막 생성/편집 페이지"""
    return templates.TemplateResponse("pages/subtitle_gen.html", {
        "request": request,
        "page": "subtitle-gen",
        "title": "자막 편집"
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

@app.get("/settings", response_class=HTMLResponse)
async def page_settings(request: Request):
    """설정 페이지"""
    return templates.TemplateResponse("pages/settings.html", {
        "request": request,
        "page": "settings",
        "title": "설정"
    })


# ===========================================
# API: 프로젝트 관리
# ===========================================

@app.get("/api/projects")
async def get_projects():
    """모든 프로젝트 목록 (상태 포함)"""
    return {"projects": db.get_projects_with_status()}

@app.post("/api/projects")
async def create_project(req: ProjectCreate):
    """새 프로젝트 생성"""
    project_id = db.create_project(req.name, req.topic)
    
    # 언어 설정 저장
    if req.target_language:
        db.update_project_setting(project_id, 'target_language', req.target_language)
        
    return {"status": "ok", "project_id": project_id}

@app.get("/api/projects/{project_id}")
async def get_project(project_id: int):
    """프로젝트 상세 조회"""
    project = db.get_project(project_id)
    if not project:
        raise HTTPException(404, "프로젝트를 찾을 수 없습니다")
    return project

@app.get("/api/projects/{project_id}/full")
async def get_project_full(project_id: int):
    """프로젝트 전체 데이터 조회"""
    data = db.get_project_full_data(project_id)
    if not data:
        raise HTTPException(404, "프로젝트를 찾을 수 없습니다")
    return data

@app.put("/api/projects/{project_id}")
async def update_project(project_id: int, req: ProjectUpdate):
    """프로젝트 업데이트"""
    updates = {k: v for k, v in req.dict().items() if v is not None}
    if updates:
        db.update_project(project_id, **updates)
    return {"status": "ok"}

@app.post("/api/projects/{project_id}/settings")
async def save_project_settings(project_id: int, req: ProjectSettingsSave):
    """프로젝트 상세 설정 (자막, 비디오 등) 저장"""
    settings = req.dict(exclude_unset=True)
    if not settings:
         return {"status": "ok", "message": "No changes"}
         
    for key, value in settings.items():
        # Enum to string conversion if needed
        db.update_project_setting(project_id, key, value)
        
    return {"status": "ok", "message": "Settings saved"}

@app.delete("/api/projects/{project_id}")
async def delete_project(project_id: int):
    """프로젝트 삭제"""
    try:
        db.delete_project(project_id)
        return {"status": "ok"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.patch("/api/projects/{project_id}")
async def update_project_details(project_id: int, data: Dict[str, Any]):
    """프로젝트 정보 (이름, 주제, 제목) 업데이트"""
    try:
        # 1. projects 테이블 정보 업데이트 (name, topic)
        project_updates = {}
        if "name" in data: project_updates["name"] = data["name"]
        if "topic" in data: project_updates["topic"] = data["topic"]
        
        if project_updates:
            db.update_project(project_id, **project_updates)
            
        # 2. project_settings 테이블 정보 업데이트 (title -> video_title)
        if "video_title" in data:
            db.update_project_setting(project_id, "title", data["video_title"])
            
        return {"status": "ok"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/projects/{project_id}/analysis")
async def save_analysis(project_id: int, req: AnalysisSave, background_tasks: BackgroundTasks):
    """분석 결과 저장"""
    db.save_analysis(project_id, req.video_data, req.analysis_result)
    db.update_project(project_id, status="analyzed")
    
    # [NEW] 프로젝트 설정에서 스타일 가져오기 (기본값 story)
    settings = db.get_project_settings(project_id)
    script_style = settings.get('script_style', 'story') if settings else 'story'
    
    # [NEW] 성공 전략 학습 (백그라운드 실행)
    background_tasks.add_task(
        background_learn_strategy, 
        req.video_data.get('id'), 
        req.analysis_result,
        script_style
    )
    
    return {"status": "ok"}

@app.get("/api/projects/{project_id}/analysis")
async def get_analysis(project_id: int):
    """분석 결과 조회"""
    return db.get_analysis(project_id) or {}

@app.post("/api/projects/{project_id}/script-structure")
async def save_script_structure(project_id: int, req: ScriptStructureSave):
    """대본 구조 저장"""
    db.save_script_structure(project_id, req.dict())
    db.update_project(project_id, status="planned")
    return {"status": "ok"}

@app.get("/api/projects/{project_id}/script-structure")
async def get_script_structure(project_id: int):
    """대본 구조 조회"""
    return db.get_script_structure(project_id) or {}


@app.post("/api/projects/{project_id}/script-structure/auto")
async def auto_generate_script_structure(project_id: int):
    """대본 구조 자동 생성 (분석 결과 기반)"""
    # 1. 분석 결과 조회
    analysis = db.get_analysis(project_id)
    if not analysis or not analysis.get("analysis_result"):
        raise HTTPException(400, "분석 데이터가 없습니다. 먼저 분석을 진행해주세요.")

    # 2. Gemini를 사용하여 구조 생성
    from services.gemini_service import gemini_service
    structure = await gemini_service.generate_script_structure(analysis["analysis_result"])
    
    if "error" in structure:
        raise HTTPException(500, f"구조 생성 실패: {structure['error']}")

    # 3. DB 저장
    db.save_script_structure(project_id, structure)
    db.update_project(project_id, status="planned")

    return {"status": "ok", "structure": structure}

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

@app.get("/api/projects/{project_id}/script")
async def get_script(project_id: int):
    """대본 조회"""
    return db.get_script(project_id) or {}


@app.post("/api/projects/{project_id}/image-prompts/auto")
async def auto_generate_images(project_id: int):
    """대본 기반 이미지 프롬프트 생성 및 일괄 이미지 생성"""
    # 1. 대본 조회
    script_data = db.get_script(project_id)
    if not script_data or not script_data.get("full_script"):
        raise HTTPException(400, "대본이 없습니다. 먼저 대본을 생성해주세요.")
    
    script = script_data["full_script"]
    duration = script_data.get("estimated_duration", 60)

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
        # TTS 테이블 구조에 맞게 저장 (provider='external', voice_id='upload')
        db.save_tts_result(project_id, file_path, "external", "upload", "ko", 1.0)
        
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
    return {"prompts": db.get_image_prompts(project_id)}

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
    """썸네일 아이디어 저장"""
    db.save_thumbnails(project_id, req.ideas, req.texts)
    return {"status": "ok"}

@app.get("/api/projects/{project_id}/thumbnails")
async def get_thumbnails(project_id: int):
    """썸네일 아이디어 조회"""
    return db.get_thumbnails(project_id) or {}

@app.post("/api/projects/{project_id}/thumbnail/save")
async def save_client_thumbnail(project_id: int, file: UploadFile = File(...)):
    """클라이언트 캔버스에서 생성된 썸네일 이미지 저장"""
    try:
        # 1. 출력 경로 확보
        output_dir, web_dir = get_project_output_dir(project_id)
        
        # 2. 유니크 파일명
        import time
        filename = f"thumb_{project_id}_{int(time.time())}.png"
        file_path = os.path.join(output_dir, filename)
        web_url = f"{web_dir}/{filename}"
        
        # 3. 저장
        content = await file.read()
        with open(file_path, "wb") as f:
            f.write(content)
            
        # 4. DB 업데이트
        db.update_project_setting(project_id, 'thumbnail_url', web_url)
        
        return {"status": "ok", "url": web_url, "path": file_path}
    except Exception as e:
        print(f"Error saving thumbnail: {e}")
        return JSONResponse(status_code=500, content={"error": str(e)})

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
        # video_path 설정이 있으면 렌더링 시 그게 우선될 수 있으므로, 여기서도 초기화하거나 
        # 명시적으로 background_video_url을 업데이트
        db.update_project_setting(project_id, 'background_video_url', web_url)
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

@app.get("/api/projects/{project_id}/full")
async def get_project_full(project_id: int):
    """프로젝트 전체 데이터 조회 (상태 복구용)"""
    data = db.get_project_full_data(project_id)
    if not data:
        raise HTTPException(404, "프로젝트를 찾을 수 없습니다.")
    return data

@app.get("/api/projects/{project_id}/shorts")
async def get_shorts(project_id: int):
    """쇼츠 조회"""
    return db.get_shorts(project_id) or {}

# 프로젝트 핵심 설정 (10가지 요소)
@app.post("/api/projects/{project_id}/settings")
async def save_project_settings(project_id: int, req: ProjectSettingsSave):
    """프로젝트 핵심 설정 저장"""
    settings = {k: v for k, v in req.dict().items() if v is not None}
    db.save_project_settings(project_id, settings)
    return {"status": "ok"}

@app.get("/api/projects/{project_id}/settings")
async def get_project_settings(project_id: int):
    """프로젝트 핵심 설정 조회"""
    return db.get_project_settings(project_id) or {}

@app.patch("/api/projects/{project_id}/settings/{key}")
async def update_project_setting(project_id: int, key: str, value: str):
    """단일 설정 업데이트"""
    # 숫자 변환
    if key in ['duration_seconds', 'is_uploaded', 'subtitle_font_size']:
        value = int(value)
    elif key in ['subtitle_stroke_width']:
        value = float(value)
    result = db.update_project_setting(project_id, key, value)
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

@app.get("/api/settings/api-keys")
async def get_api_keys():
    """API 키 상태 조회 (마스킹)"""
    return config.get_api_keys_status()

@app.post("/api/settings/api-keys")
async def save_api_keys(req: ApiKeySave):
    """API 키 저장"""
    updated = []

    if req.youtube is not None and req.youtube.strip():
        config.update_api_key('YOUTUBE_API_KEY', req.youtube.strip())
        updated.append('youtube')

    if req.gemini is not None and req.gemini.strip():
        config.update_api_key('GEMINI_API_KEY', req.gemini.strip())
        updated.append('gemini')

    if req.elevenlabs is not None and req.elevenlabs.strip():
        config.update_api_key('ELEVENLABS_API_KEY', req.elevenlabs.strip())
        updated.append('elevenlabs')

    if req.typecast is not None and req.typecast.strip():
        config.update_api_key('TYPECAST_API_KEY', req.typecast.strip())
        updated.append('typecast')

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
    return settings_service.get_settings()

@app.post("/api/settings")
async def save_global_settings(data: Dict[str, Any] = Body(...)):
    """글로벌 설정 저장"""
    from services.settings_service import settings_service
    settings_service.save_settings(data)
    return {"status": "ok"}


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
                
                # 가급적 pydub 사용 (더 안정적)
                try:
                    from pydub import AudioSegment
                    import imageio_ffmpeg
                    
                    # ffmpeg 경로 수동 설정
                    ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
                    AudioSegment.converter = ffmpeg_exe
                    
                    combined = AudioSegment.empty()
                    for af in audio_files:
                        segment_audio = AudioSegment.from_file(af)
                        combined += segment_audio
                    
                    combined.export(result_filename, format="mp3")
                    output_path = result_filename
                    print(f"✅ [Main] pydub으로 오디오 병합 완료: {result_filename}")
                except Exception as pydub_err:
                    print(f"⚠️ pydub 병합 실패 ({pydub_err}), MoviePy로 재시도합니다.")
                    try:
                        try:
                            from moviepy.editor import AudioFileClip, concatenate_audioclips
                        except ImportError:
                            from moviepy import AudioFileClip, concatenate_audioclips
                    except ImportError:
                        from moviepy.audio.io.AudioFileClip import AudioFileClip
                        from moviepy.audio.AudioClip import concatenate_audioclips
                    
                    clips = []
                    for af in audio_files:
                        try:
                            clips.append(AudioFileClip(af))
                        except:
                            pass
                    
                    if clips:
                        final_clip = concatenate_audioclips(clips)
                        final_clip.write_audiofile(result_filename, verbose=False, logger=None)
                        final_clip.close()
                        for clip in clips: clip.close() # 모든 클립 리소스 해제
                        output_path = result_filename
                        print(f"✅ [Main] MoviePy로 오디오 병합 완료: {result_filename}")
                
                if output_path:
                    # 임시 파일 삭제
                    for af in audio_files:
                         try: os.remove(af)
                         except: pass
                else:
                    return {"status": "error", "error": "오디오 병합 과정에서 모든 시도가 실패했습니다."}
            else:
                 return {"status": "error", "error": "생성된 오디오 세그먼트가 없습니다."}

        # ----------------------------------------------------------------
        # 일반(단일) 모드 처리
        # ----------------------------------------------------------------
        else:
            # 1. ElevenLabs
            if req.provider == "elevenlabs":
                output_path = await tts_service.generate_elevenlabs(
                    req.text, req.voice_id, result_filename
                )
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
                 # save_tts(project_id, voice_id, voice_name, audio_path, duration)
                 # duration은 현재 계산하지 않으므로 0으로 저장
                 db.save_tts(
                     req.project_id,
                     req.voice_id or "multi-voice" if req.multi_voice else "default",
                     req.voice_id or "multi-voice" if req.multi_voice else "default",
                     output_path,
                     0
                 )
                 
                 # [FIX] 자막 생성을 위해 TTS 입력 텍스트를 프로젝트 설정(script)에 저장
                 if req.text:
                     db.update_project_setting(req.project_id, "script", req.text)
                     print(f"DEBUG: Saved TTS text to project settings (len={len(req.text)})")

             except Exception as db_e:
                 print(f"TTS DB 저장 실패: {db_e}")
        
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
                            "provider": "elevenlabs",
                            "voice_id": v["voice_id"],
                            "name": v["name"],
                            "labels": v.get("labels", {})
                        })
        except:
            pass

    return {"voices": voices}


# ===========================================
# API: 이미지 생성 (Gemini Imagen 3)
# ===========================================

class ImageGenerateRequest(BaseModel):
    prompt: str
    aspect_ratio: str = "9:16"  # 숏폼 전용 (9:16)


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
        # negative_constraints 강화 (CJK 포함)
        negative_constraints = "text, words, letters, alphabet, typography, watermark, signature, speech bubble, logo, brand name, writing, caption, chinese characters, japanese kanji, korean hangul, hanzi"
        
        # 프롬프트 앞뒤로 강력한 부정 명령 배치
        final_prompt = f"ABSOLUTELY NO TEXT. NO CHINESE/JAPANESE/KOREAN CHARACTERS. {clean_prompt}. Background image only. High quality, 8k, detailed, YouTube thumbnail background, empty background, no watermark. DO NOT INCLUDE: {negative_constraints}. INVISIBLE TEXT."

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

        # 2. 이미지 저장
        img_data = response.generated_images[0].image._pil_image
        
        # static/img/thumbnails 폴더 확보
        save_dir = "static/img/thumbnails"
        os.makedirs(save_dir, exist_ok=True)
        
        filename = f"bg_{uuid.uuid4().hex}.png"
        filepath = os.path.join(save_dir, filename)
        
        img_data.save(filepath, format="PNG")
        
        # URL 및 절대 경로 반환
        return {
            "status": "ok",
            "url": f"/static/img/thumbnails/{filename}",
            "path": os.path.abspath(filepath)
        }

    except Exception as e:
        print(f"Error generating background: {e}")
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
        img = None
        
        if req.background_path and os.path.exists(req.background_path):
            # 기존 이미지 로드
            try:
                img = Image.open(req.background_path)
                img = img.resize((1280, 720), Image.LANCZOS)
                print(f"Loaded background from: {req.background_path}")
            except Exception as e:
                print(f"Failed to load background: {e}")
                # Fallback to generation if load fails? Or error? Let's error for clarity.
                raise HTTPException(400, f"배경 이미지 로드 실패: {str(e)}")
        else:
            # Generate new image
            from google import genai
            client = genai.Client(api_key=config.GEMINI_API_KEY)

            # 1. Imagen 4로 배경 이미지 생성 (무조건 텍스트 생성 억제)
            clean_prompt = req.prompt
            
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






@app.post("/api/image/generate-prompts")
async def generate_image_prompts(req: PromptsGenerateRequest):
    """대본 기반 이미지 프롬프트 생성 (POST Body 사용)"""
    script = req.script
    style = req.style
    count = req.count
    
    # [NEW] 이미지 개수 처리 로직
    if count > 0:
        count_instruction = f"- {count}개의 이미지 프롬프트를 생성하세요 (지정된 개수 준수)"
    else:
        count_instruction = "- 대본의 흐름과 내용을 분석하여 **자연스러운 장면 전환에 필요한 적절한 수**의 이미지 프롬프트를 생성하세요 (개수는 AI가 판단)"

    # [NEW] 스타일 매핑 로직
    style_prompts = {
        "realistic": "A highly realistic photo, 8k resolution, highly detailed photography, standard view",
        "anime": "Anime style illustration, vibrant colors, detailed background, Makoto Shinkai style",
        "cinematic": "Cinematic movie shot, dramatic lighting, shallow depth of field, anamorphic lens",
        "minimal": "Minimalist flat vector illustration, simple shapes, clean lines, white background",
        "3d": "3D render, Pixar style, soft studio lighting, octane render, 4k",
        "webtoon": "Oriental fantasy webtoon style illustration of a character in traditional clothing lying on a bed in a dark room, dramatic lighting, detailed line art, manhwa aesthetics, high quality"
    }
    
    # 선택된 스타일의 상세 프롬프트 가져오기 (없으면 입력값 그대로 사용)
    detailed_style = style_prompts.get(style.lower(), style)

    prompt = f"""당신은 AI 이미지 생성 프롬프트 전문가입니다.
아래 대본을 읽고, 영상에 사용할 이미지 프롬프트를 생성해주세요.

[대본]
{script}  # [MODIFIED] 길이 제한 해제

[스타일 지침]
"{detailed_style}"
모든 이미지 프롬프트에 위 스타일 키워드를 반드시 포함시켜야 합니다.

[요청]
{count_instruction}
- 각 프롬프트는 영어로 작성하세요
- Midjourney/DALL-E에 적합한 형식으로 작성하세요
- 프롬프트 시작 부분에 스타일 키워드를 배치하세요.
- **장시간 영상 페이싱 지침**: 사용자의 몰입도 유지를 위해 다음 구간별 빈도를 준수하세요:
  1. 0~2분: 8초당 1장 (고속 후킹)
  2. 2~5분: 20초당 1장 (몰입 전개)
  3. 5~7분: 40초당 1장 (안정 전개)
  4. 7~10분: 1분당 1장 (유지 전개)
  5. 10분 이후: 2~10분당 1장 (매크로 흐름)

JSON 형식으로 반환:
{{
    "prompts": [
        {{"scene": "장면 설명 (한국어)", "prompt": "{style}, 영어 프롬프트", "style_tags": "--ar 1:1"}}
    ]
}}

JSON만 반환하세요."""

    result = await gemini_generate(GeminiRequest(prompt=prompt, temperature=0.7))

    if result["status"] == "ok":
        json_match = re.search(r'\{[\s\S]*\}', result["text"])
        if json_match:
            try:
                return json.loads(json_match.group())
            except:
                pass
        return {"raw": result["text"]}

    return result


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
        # 이미지 생성 (Gemini Imagen)
        images_bytes = await gemini_service.generate_image(
            prompt=prompt,
            num_images=1,
            aspect_ratio=aspect_ratio
        )

        if not images_bytes:
            return {"status": "error", "error": "이미지가 생성되지 않았습니다."}
        
        # 프로젝트별 폴더 경로 가져오기
        output_dir, web_dir = get_project_output_dir(project_id)
        
        filename = f"p{project_id}_s{scene_number}_{int(datetime.datetime.now().timestamp())}.png"
        output_path = os.path.join(output_dir, filename)
        
        # 파일 저장
        with open(output_path, "wb") as f:
            f.write(images_bytes[0])
            
        image_url = f"{web_dir}/{filename}"
        
        # DB 업데이트 (이미지 URL 저장)
        print(f"DEBUG: Updating DB for Project {project_id}, Scene {scene_number} with URL {image_url}")
        db.update_image_prompt_url(project_id, scene_number, image_url)
        
        return {
            "status": "ok",
            "image_url": image_url
        }

    except Exception as e:
        print(f"이미지 생성 실패: {e}")
        import traceback
        traceback.print_exc()
        return {"status": "error", "error": str(e)}

@app.get("/api/debug/dump_image_prompts/{project_id}")
async def debug_dump_image_prompts(project_id: int):
    try:
        data = db.get_image_prompts(project_id)
        return {"count": len(data), "data": data}
    except Exception as e:
        return {"error": str(e)}


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
        
        # 데이터베이스에 경로 저장
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
# API: 영상 생성
# ===========================================

@app.post("/api/video/create-slideshow")
async def create_slideshow(
    background_tasks: BackgroundTasks,
    images: List[str],
    audio_url: Optional[str] = None,
    duration_per_image: float = 5.0
):
    """이미지 슬라이드쇼 영상 생성"""
    from services.video_service import video_service


 
    now_kst = config.get_kst_time()
    output_filename = f"video_{now_kst.strftime('%Y%m%d_%H%M%S')}.mp4"

    # 백그라운드에서 처리 (함수 래퍼 정의)
    async def process_video_generation():
        try:
            # 1. 슬라이드쇼 영상 생성
            video_path = video_service.create_slideshow(
                images=images,
                audio_path=audio_url,
                output_filename=output_filename,
                duration_per_image=duration_per_image
            )
            
            # 2. 오디오가 있다면 자막 자동 생성 및 합성 (MVP)
            if audio_url:
                # 오디오 길이 가져오기
                try:
                    from moviepy.editor import AudioFileClip
                    audio_clip = AudioFileClip(audio_url)
                    duration = audio_clip.duration
                    audio_clip.close()
                    
                    # 대본이 없으므로 지금은 임시 텍스트나, DB에서 대본을 가져와야 함.
                    # 하지만 현재 API 구조상 project_id를 받지 않고 있음.
                    # 따라서 이 엔드포인트를 수정하여 project_id를 받도록 하거나,
                    # MVP 단계에서는 "자막 생성 중" 로그만 남기고 추후 통합
                    print(f"영상 생성 완료: {video_path}")
                    
                except Exception as e:
                    print(f"자막 처리 중 오류: {e}")

        except Exception as e:
            print(f"영상 생성 실패: {e}")

    background_tasks.add_task(process_video_generation)

    return {
        "status": "processing",
        "message": "영상 생성 시작",
        "output_file": output_filename
    }


class RenderRequest(BaseModel):
    project_id: Union[int, str]
    use_subtitles: bool = True
    resolution: str = "1080p" # 1080p or 720p

class SubtitleGenerationRequest(BaseModel):
    project_id: Union[int, str]
    text: Optional[str] = None

@app.post("/api/subtitle/generate")
async def generate_subtitle_api(
    request: SubtitleGenerationRequest,
):
    """TTS 오디오 기반 자막 생성"""
    project_id = int(request.project_id) # Ensure int
    print(f"DEBUG: Generating subtitles for project {project_id}")
    
    # [FIX] 요청에 텍스트가 포함되어 있으면 프로젝트 설정에 저장 (즉시 반영)
    if request.text:
         db.update_project_setting(project_id, "script", request.text)
         print(f"DEBUG: Updated project script from request text (len={len(request.text)})")

    try:
        # 1. TTS 오디오 확인
        tts_data = db.get_tts(project_id)
        if not tts_data or not tts_data.get('audio_path'):
            print(f"DEBUG: No TTS data for project {project_id}")
            return {"status": "error", "error": "TTS 오디오가 없습니다. 먼저 음성을 생성해주세요."}
            
        audio_path = tts_data['audio_path']
        if not os.path.exists(audio_path):
             return {"status": "error", "error": "오디오 파일을 찾을 수 없습니다."}

        # 2. 자막 생성
        import services.video_service as vs
        subtitles = vs.video_service.generate_aligned_subtitles(audio_path)
        
        if not subtitles:
            # 실패시 대본 기반 단순 생성 시도
            script_text = ""
            # 요청에 텍스트가 있으면 최우선 사용
            if request.text:
                script_text = request.text
            else:
                script_data = db.get_script(project_id)
                if script_data and script_data.get('full_script'):
                    script_text = script_data['full_script']
                else:
                     # script table에 없으면 settings 확인
                     settings = db.get_project_settings(project_id)
                     if settings and settings.get('script'):
                         script_text = settings['script']
            
            if script_text:
                print("Whisper failed/empty, falling back to simple script split.")
                duration = tts_data.get('duration', 0)
                
                # Duration이 0이거나 너무 작으면 실제 파일에서 측정 (필수 Fix)
                if duration <= 1:
                     try:
                         from moviepy.editor import AudioFileClip
                         # AudioFileClip은 무거우므로 짧게 사용
                         with AudioFileClip(audio_path) as audio_clip:
                             duration = audio_clip.duration
                             print(f"DEBUG: Calculated actual audio duration: {duration}s")
                             
                             # DB에 올바른 Duration 업데이트 (영구 수정)
                             # save_tts(project_id, voice_id, voice_name, audio_path, duration)
                             if tts_data.get('voice_id'): # 데이터가 온전하다면
                                 db.save_tts(
                                     project_id, 
                                     tts_data['voice_id'], 
                                     tts_data['voice_name'], 
                                     audio_path, 
                                     duration
                                 )
                     except Exception as e:
                         print(f"Failed to calculate audio duration: {e}")
                         duration = 60 # 최후의 수단
                
                subtitles = vs.video_service.generate_simple_subtitles(script_text, duration)
            else:
                print("DEBUG: No script found for fallback.")
                
        # 3. 최후의 수단 (Last Resort): 빈 자막 1개 생성 (사용자가 편집할 수 있도록)
        if not subtitles:
             print("DEBUG: All generation methods failed. Creating empty placeholder.")
             duration = tts_data.get('duration', 10)
             if duration == 0 and os.path.exists(audio_path):
                 try:
                     from moviepy.editor import AudioFileClip
                     ac = AudioFileClip(audio_path)
                     duration = ac.duration
                     ac.close()
                 except:
                     duration = 10
             
             subtitles.append({
                 "start": 0.0,
                 "end": float(f"{duration:.2f}"),
                 "text": "생성된 자막이 없습니다. 여기에 내용을 입력하세요."
             })

        # 4. 저장
        if subtitles:
            # JSON 파일로 저장
            output_dir, web_dir = get_project_output_dir(project_id)
            save_path = os.path.join(output_dir, f"subtitles_{project_id}.json")
            
            import json
            with open(save_path, "w", encoding="utf-8") as f:
                json.dump(subtitles, f, ensure_ascii=False, indent=2)
                
            print(f"DEBUG: 자막 자동 저장 완료 ({len(subtitles)} lines) -> {save_path}")
            
        else:
            return {"status": "error", "error": "자막을 생성할 수 없습니다."}

    except Exception as e:
        print(f"Subtitle gen failed: {e}")
        return {"status": "error", "error": str(e)}

    # Check how save is handled in existing code (need to view main.py more)
    # The view_file showed up to 1400. I need to see subtitle APIs.
    return {"status": "ok", "subtitles": subtitles}

    class Config:
        extra = "ignore"

@app.post("/api/projects/{project_id}/render")
async def render_project_video(
    project_id: int,
    request: RenderRequest,
    background_tasks: BackgroundTasks
):
    """프로젝트 영상 최종 렌더링 (이미지 + 오디오 + 자막)"""
    try:
        # 해상도 설정 (기본 16:9 롱폼)
        target_resolution = (1920, 1080)
        if request.resolution == "720p":
            target_resolution = (1280, 720)
        
        # 1. 데이터 조회
        images_data = db.get_image_prompts(project_id)
        tts_data = db.get_tts(project_id)
        script_data = db.get_script(project_id)
        
        if not images_data:
            raise HTTPException(400, "이미지 데이터가 없습니다.")
        if not tts_data:
            raise HTTPException(400, "TTS 오디오 데이터가 없습니다.")
        
        # 이미지 경로 리스트 추출 (순서대로)
        # 이미지 URL이 /output/ 으로 시작하므로 실제 파일 경로로 변환
        images = []
        for img in images_data:
            if img.get("image_url"):
                # URL: /static/images/1/filename.png
                # Path: config.STATIC_DIR / images / 1 / filename.png
                if img["image_url"].startswith("/static/"):
                    relative_path = img["image_url"].replace("/static/", "", 1)
                    # Windows 경로 구분자로 변경 (필요 시)
                    relative_path = relative_path.replace("/", os.sep)
                    fpath = os.path.join(config.STATIC_DIR, relative_path)
                elif img["image_url"].startswith("/output/"):
                     # 썸네일 등 output 폴더에 있는 경우
                     relative_path = img["image_url"].replace("/output/", "", 1)
                     fpath = os.path.join(config.OUTPUT_DIR, relative_path)
                else:
                     # 기타?
                     continue

                if os.path.exists(fpath):
                    images.append(fpath)
        
        if not images:
             # [NEW] Check if Background Video is set
             project_settings = db.get_project_settings(project_id)
             bg_video_url = project_settings.get("background_video_url")
             if not bg_video_url:
                 raise HTTPException(400, "유효한 이미지 파일 또는 배경 동영상이 없습니다.")
        else:
             project_settings = db.get_project_settings(project_id)
             bg_video_url = project_settings.get("background_video_url")
            
        # 오디오 경로
        audio_path = tts_data.get("audio_path")
        if not audio_path or not os.path.exists(audio_path):
            raise HTTPException(400, "오디오 파일을 찾을 수 없습니다.")

        # 2. 백그라운드 렌더링 준비
        from services.video_service import video_service
        
        # 프로젝트별 출력 폴더 확보
        output_dir, web_dir = get_project_output_dir(project_id)
        
        now_kst = config.get_kst_time()
        # 최종 파일명 (절대 경로)
        final_output_filename = f"final_{project_id}_{now_kst.strftime('%Y%m%d_%H%M%S')}.mp4"
        final_output_path = os.path.join(output_dir, final_output_filename)

        def render_executor_func(target_dir_arg, use_subtitles_arg, target_resolution_arg, bg_video_url_arg):
            # 몽키패치: MoviePy 구버전 호환성 해결
            import PIL.Image
            if not hasattr(PIL.Image, 'ANTIALIAS'):
                PIL.Image.ANTIALIAS = PIL.Image.LANCZOS

            try:
                with open(config.DEBUG_LOG_PATH, "a", encoding="utf-8") as rf:
                    rf.write(f"[{datetime.datetime.now()}] Starting Single-pass render for project {project_id}\n")
                    rf.write(f"[{datetime.datetime.now()}] Images: {len(images)}, Audio: {audio_path}\n")

                # 1. 자막 데이터 및 설정 준비 (단일 패스용)
                subs = []
                s_settings = {}
                if use_subtitles_arg:
                    # 자막 스타일 설정 로드
                    s_settings = db.get_project_settings(project_id) or {}
                    s_settings = {
                        "font": s_settings.get("subtitle_font", config.DEFAULT_FONT_PATH),
                        "font_color": s_settings.get("subtitle_color", "white"),
                        "style_name": s_settings.get("subtitle_style_enum", "Basic_White"),
                        "font_size": s_settings.get("subtitle_font_size", 80),
                        "stroke_color": s_settings.get("subtitle_stroke_color", "black"),
                        "stroke_color": s_settings.get("subtitle_stroke_color", "black"),
                        "stroke_width": s_settings.get("subtitle_stroke_width", 5),
                        "position_y": s_settings.get("subtitle_position_y")
                    }
                    print(f"DEBUG_RENDER: main.py prepared s_settings: {s_settings}") # [DEBUG] Logic Trace

                    # 자막 데이터 로드
                    inner_output_dir, _ = get_project_output_dir(project_id)
                    saved_sub_path = os.path.join(inner_output_dir, f"subtitles_{project_id}.json")
                    
                    if os.path.exists(saved_sub_path):
                        import json
                        with open(saved_sub_path, "r", encoding="utf-8") as f:
                            subs = json.load(f)
                    
                    if not subs:
                        # Fallback: 스크립트 기반 정렬 자막 생성
                        script = script_data.get("full_script") if script_data else ""
                        subs = video_service.generate_aligned_subtitles(audio_path, script)

                # 2. 오디오 정보
                from moviepy.editor import AudioFileClip
                audio_clip = AudioFileClip(audio_path)
                audio_duration = audio_clip.duration
                audio_clip.close()
                
                duration_per_image = audio_duration / len(images)
                
                # 3. 단일 패스 영상 생성 (이미지 + 오디오 + 자막 통합)
                video_path = video_service.create_slideshow(
                    images=images,
                    audio_path=audio_path,
                    output_filename=final_output_path, # 바로 최종 경로로 생성
                    duration_per_image=duration_per_image,
                    resolution=target_resolution_arg,
                    title_text="",
                    project_id=project_id,
                    subtitles=subs if use_subtitles_arg else None,

                    subtitle_settings=s_settings if use_subtitles_arg else None,
                    background_video_url=bg_video_url_arg
                )
                
                final_path = video_path

                # C. DB 업데이트
                # 웹 경로: /output/Project_Date/video.mp4
                web_video_path = f"{web_dir}/{os.path.basename(final_path)}"
                db.update_project_setting(project_id, "video_path", web_video_path)
                db.update_project(project_id, status="rendered")
                print(f"프로젝트 {project_id} 단일 패스 렌더링 완료: {final_path}")

            except Exception as e:
                import traceback
                error_msg = f"프로젝트 렌더링 실패: {e}"
                print(error_msg)
                traceback.print_exc()
                
                try:
                    with open(config.DEBUG_LOG_PATH, "a", encoding="utf-8") as rf:
                         rf.write(f"[{datetime.datetime.now()}] Render Error: {e}\n{traceback.format_exc()}\n")
                except:
                    pass
                
                db.update_project(project_id, status="failed")

        print(f"Adding background task for project {project_id}")
        try:
                rf.write(f"[{datetime.datetime.now()}] Scheduled task for project {project_id}\n")
        except Exception as e:
            print(f"Log Error: {e}")

        # 0. 상태 업데이트 (렌더링 시작) - 기존 video_path 제거하여 프론트엔드 폴링시 '완료'로 오해하지 않도록 함
        db.update_project(project_id, status="rendering")
        db.update_project_setting(project_id, "video_path", "")

        # background_tasks.add_task(render_executor_func, output_dir)
        background_tasks.add_task(render_executor_func, target_dir_arg=output_dir, use_subtitles_arg=request.use_subtitles, target_resolution_arg=target_resolution, bg_video_url_arg=bg_video_url)

        return {
            "status": "processing",
            "message": "최종 영상 렌더링이 시작되었습니다.",
            "output_file": final_output_filename
        }

    except HTTPException as he:
        raise he
    except Exception as e:
        import traceback
        from fastapi.responses import JSONResponse
        error_msg = f"렌더링 요청 처리 중 오류: {str(e)}"
        print(error_msg)
        traceback.print_exc()
        return JSONResponse(status_code=500, content={"error": error_msg, "traceback": traceback.format_exc()})


@app.post("/api/projects/{project_id}/upload")
async def upload_project_video(
    project_id: int,
    privacy_status: str = "private", # public, unlisted, private
    publish_at: Optional[str] = None # ISO 8601 (e.g. 2024-12-25T10:00:00Z)
):
    """프로젝트 영상 유튜브 업로드 (예약 발행 지원)"""
    from services.youtube_upload_service import youtube_upload_service

    # 1. 데이터 조회
    project = db.get_project(project_id)
    settings = db.get_project_settings(project_id)
    metadata = db.get_metadata(project_id)
    
    if not settings or not settings.get("video_path") or not os.path.exists(os.path.join(config.OUTPUT_DIR, os.path.basename(settings["video_path"]))):
        raise HTTPException(400, "렌더링된 영상이 없습니다. 먼저 영상을 생성해주세요.")

    video_path = os.path.join(config.OUTPUT_DIR, os.path.basename(settings["video_path"]))
    
    # 2. 메타데이터 구성
    title = settings.get("title", f"Project {project_id}")
    description = ""
    tags = []
    
    if metadata:
        if metadata.get("titles"):
            title = metadata["titles"][0] # 첫 번째 추천 제목 사용
        description = metadata.get("description", "")
        # 태그와 해시태그 합치기
        tags = (metadata.get("tags", []) + metadata.get("hashtags", []))[:15] # 15개 제한

    # 3. 설명 보강 (자동 생성된 문구가 너무 짧을 경우)
    if not description:
        description = f"""
{title}

#Shorts #YouTubeShorts

(Generated by 피카디리스튜디오)
        """.strip()

    # 4. 업로드 실행 (동기 실행 - 브라우저 인증이 필요할 수 있으므로 백그라운드 대신 동기로 처리)
    try:
        response = youtube_upload_service.upload_video(
            file_path=video_path,
            title=title,
            description=description,
            tags=tags,
            privacy_status=privacy_status,
            publish_at=publish_at
        )
        
        # 5. DB 업데이트
        db.update_project_setting(project_id, "is_uploaded", 1)
        
        return {
            "status": "ok",
            "video_id": response.get("id"),
            "url": f"https://youtu.be/{response.get('id')}"
        }
        
    except Exception as e:
        print(f"업로드 실패: {e}")
        return {"status": "error", "error": str(e)}




# ===========================================
# Subtitle Routes
# ===========================================

@app.get("/subtitle-gen", response_class=HTMLResponse)
async def subtitle_gen_page(request: Request):
    return templates.TemplateResponse("pages/subtitle_gen.html", {
        "request": request,
        "title": "자막 생성 및 편집",
        "page": "subtitle-gen"
    })

@app.get("/api/subtitle/{project_id}")
async def get_subtitle(project_id: int):
    """프로젝트의 자막 정보 조회 (VTT -> JSON 변환하여 반환)"""
    try:
        # [AUTO RECOVERY] 먼저 자동 복구 시도 (파일은 있는데 DB만 없는 경우 대비)
        # 이미지/오디오 모두 스캔
        recover_project_assets(project_id)
        
        tts_data = db.get_tts(project_id)
        if not tts_data or not tts_data.get("audio_path"):
            return {"status": "error", "error": "TTS 데이터가 없습니다."}
        
        audio_path = tts_data["audio_path"]
        vtt_path = audio_path.replace(".mp3", ".vtt")
        
        subtitles = []
        
        # 1. 편집된/생성된 자막 JSON 로드 (우선순위 1)
        output_dir, web_dir = get_project_output_dir(project_id)
        saved_sub_path = os.path.join(output_dir, f"subtitles_{project_id}.json")
        
        if os.path.exists(saved_sub_path):
            import json
            try:
                with open(saved_sub_path, "r", encoding="utf-8") as f:
                    subtitles = json.load(f)
            except Exception as e:
                print(f"Error loading saved subtitles: {e}")
                pass

        # 2. Edge TTS로 생성된 VTT가 있으면 폴백 (우선순위 2)
        if not subtitles and os.path.exists(vtt_path):
            try:
                import webvtt
                # webvtt 라이브러리가 있으면 사용
                for caption in webvtt.read(vtt_path):
                    subtitles.append({
                        "start": caption.start_in_seconds,
                        "end": caption.end_in_seconds,
                        "text": caption.text
                    })
            except ImportError:
                print("webvtt library not found, using manual parser")
                # Simple VTT Parser Fallback
                try:
                    with open(vtt_path, "r", encoding="utf-8") as f:
                        lines = f.readlines()
                    
                    current_caption = None
                    for line in lines:
                        line = line.strip()
                        if "-->" in line:
                            # Timecode line: 00:00:01.000 --> 00:00:04.000
                            start_str, end_str = line.split("-->")
                            
                            # Helper to convert HH:MM:SS.mmm to seconds
                            def parse_time(t_str):
                                parts = t_str.strip().split(":")
                                seconds = 0
                                if len(parts) == 3: # HH:MM:SS.mmm
                                    seconds += float(parts[0]) * 3600
                                    seconds += float(parts[1]) * 60
                                    seconds += float(parts[2])
                                elif len(parts) == 2: # MM:SS.mmm
                                    seconds += float(parts[0]) * 60
                                    seconds += float(parts[1])
                                return seconds

                            if current_caption:
                                subtitles.append(current_caption)
                            
                            current_caption = {
                                "start": parse_time(start_str),
                                "end": parse_time(end_str),
                                "text": ""
                            }
                        elif line and current_caption:
                            # Text line (skip header/metadata)
                            if not line.startswith("WEBVTT") and not line.startswith("Kind:") and not line.startswith("Language:"):
                                current_caption["text"] += line + " "
                    
                    if current_caption:
                        subtitles.append(current_caption)
                        
                except Exception as e:
                    print(f"Manual VTT parsing failed: {e}")

        # 오디오 Web URL 계산
        # audio_path가 absolute path일 때, config.OUTPUT_DIR에 대한 상대 경로 계산
        try:
            rel_path = os.path.relpath(audio_path, config.OUTPUT_DIR)
            audio_url = f"/output/{rel_path}".replace("\\", "/")
        except ValueError:
            # 경로가 다른 드라이브에 있거나 파악 불가 시
            audio_url = f"/output/{os.path.basename(audio_path)}"

        # [FIX] 이미지 리스트 조회 (자막 매칭용)
        images = []
        try:
            # DB에서 해당 프로젝트의 모든 이미지 프롬프트(및 생성된 URL) 가져오기
            prompts = db.get_image_prompts(project_id)
            # 장면 번호 순으로 정렬하여 영상 흐름과 맞춤
            prompts.sort(key=lambda x: x.get('scene_number', 0))
            # URL이 있는 것만 추출
            images = [p['image_url'] for p in prompts if p.get('image_url')]
            print(f"DEBUG: Found {len(images)} images for subtitle editor (PID: {project_id})")
        except Exception as e:
            print(f"Error loading images for subtitle: {e}")

        # [ADD] 대본 텍스트 미리 가져오기 (빈 상태일 때 자동 채움용)
        fallback_script = ""
        try:
            settings = db.get_project_settings(project_id)
            if settings and settings.get('script'):
                fallback_script = settings['script']
            else:
                script_data = db.get_script(project_id)
                if script_data and script_data.get('full_script'):
                    fallback_script = script_data['full_script']
        except Exception as e:
            print(f"Error loading fallback script: {e}")

        return {
            "status": "ok",
            "subtitles": subtitles,
            "audio_url": audio_url,
            "images": images,
            "script": fallback_script
        }
    except Exception as ie:
        import traceback
        error_msg = f"Internal Error in get_subtitle: {str(ie)}\n{traceback.format_exc()}"
        print(error_msg)
        # Write to debug file
        with open("debug_error.log", "w", encoding="utf-8") as f:
            f.write(error_msg)
        return {"status": "error", "error": f"Internal Server Error: {str(ie)}"}

@app.post("/api/subtitle/save")
async def save_subtitle(
    project_id: int = Body(...),
    subtitles: List[dict] = Body(...)
):
    """편집된 자막 저장 (및 미리보기 이미지 생성)"""
    output_dir, _ = get_project_output_dir(project_id)
    sub_path = os.path.join(output_dir, f"subtitles_{project_id}.json")
    
    # 1. 자막 저장
    import json
    with open(sub_path, "w", encoding="utf-8") as f:
        json.dump(subtitles, f, ensure_ascii=False, indent=2)
        
    db.update_project_setting(project_id, "subtitle_path", sub_path)

    # 2. 미리보기 이미지 생성 (비동기 처리 권장되나 사용자 경험 위해 동기 처리)
    # 필요한 정보 로드
    try:
        from services.video_service import video_service
        settings = db.get_project_settings(project_id)
        
        # 이미지 리스트 및 오디오 길이 (시간 매핑용)
        images = []
        if settings and settings.get('images'):
             images = settings['images']
        
        # 오디오 길이 (DB or 파일에서 확인)
        audio_data = db.get_tts(project_id)
        audio_duration = 0
        if audio_data and audio_data.get('audio_path') and os.path.exists(audio_data['audio_path']):
            try:
                from moviepy.editor import AudioFileClip
                # moviepy 로딩이 느리므로 mutagen 등으로 대체 가능하면 좋음
                # 여기선 간단히 try-catch
                clip = AudioFileClip(audio_data['audio_path'])
                audio_duration = clip.duration
                clip.close()
            except:
                pass
        
        # 스타일 정보
        font_size = settings.get('subtitle_font_size', 10)
        style_enum = settings.get('subtitle_style_enum', 'Basic_White')
        font_name = settings.get('subtitle_font', config.DEFAULT_FONT_PATH)
        font_color = settings.get('subtitle_color', 'white')
        stroke_color = settings.get('subtitle_stroke_color')
        stroke_width = settings.get('subtitle_stroke_width')

        # 각 자막에 대해 미리보기 생성
        updated_subtitles = []
        for i, sub in enumerate(subtitles):
            # 해당 시간대의 배경 이미지 찾기
            bg_image_path = None
            if images and audio_duration > 0:
                duration_per_image = audio_duration / len(images)
                mid_point = (sub['start'] + sub['end']) / 2
                img_idx = min(int(mid_point // duration_per_image), len(images) - 1)
                bg_image_path = images[img_idx]

            # 미리보기 생성
            try:
                # 배경 이미지가 웹 URL 형태일 수 있음 -> 로컬 경로로 변환 필요할 수 있음
                # DB images are usually absolute paths? Let's check.
                # Usually they are absolute paths from `image_gen`.
                
                preview_path = video_service.create_preview_image(
                    background_path=bg_image_path,
                    text=sub['text'],
                    font_size=font_size,
                    font_color=font_color,
                    font_name=font_name,
                    style_name=style_enum,
                    stroke_color=stroke_color,
                    stroke_width=stroke_width,
                    position_y=settings.get('subtitle_position_y'),
                    target_size=(1280, 720) # 16:9 Landscape
                )
                
                # 웹 URL로 변환
                filename = os.path.basename(preview_path)
                sub['preview_url'] = f"/output/{filename}"
                
            except Exception as e:
                print(f"Failed to create preview for sub {i}: {e}")
            
            updated_subtitles.append(sub)
        
        return {
            "status": "ok",
            "subtitles": updated_subtitles
        }

    except Exception as e:
        print(f"Error generating previews: {e}")
        # 실패해도 저장은 성공했으므로 ok 리턴하되 경고 로그
        return {"status": "ok", "message": "Saved but preview generation failed"}


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
    print("⏰ [Scheduler] 스케줄러가 시작되었습니다.")

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
# API: 채널 관리 (설정)
# ===========================================

@app.get("/api/channels", response_model=List[ChannelResponse])
async def get_channels():
    """등록된 채널 목록 조회"""
    conn = db.get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM channels ORDER BY created_at DESC")
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]

@app.post("/api/channels", response_model=ChannelResponse)
async def create_channel(channel: ChannelCreate):
    """채널 등록"""
    conn = db.get_db()
    cursor = conn.cursor()
    
    # 중복 체크? (핸들 기준)
    cursor.execute("SELECT id FROM channels WHERE handle = ?", (channel.handle,))
    if cursor.fetchone():
        conn.close()
        raise HTTPException(400, "이미 등록된 채널 핸들입니다.")

    cursor.execute("""
        INSERT INTO channels (name, handle, description)
        VALUES (?, ?, ?)
    """, (channel.name, channel.handle, channel.description))
    conn.commit()
    
    new_id = cursor.lastrowid
    cursor.execute("SELECT * FROM channels WHERE id = ?", (new_id,))
    row = cursor.fetchone()
    conn.close()
    
    return dict(row)

@app.delete("/api/channels/{channel_id}")
async def delete_channel(channel_id: int):
    """채널 삭제"""
    conn = db.get_db()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM channels WHERE id = ?", (channel_id,))
    conn.commit()
    conn.close()
    return {"status": "ok", "message": "채널이 삭제되었습니다."}

@app.get("/api/auth/youtube/{channel_id}")
async def authenticate_channel(channel_id: int):
    """채널별 유튜브 계정 인증 (OAuth)"""
    from services.youtube_upload_service import youtube_upload_service
    
    # 1. 채널 정보 확인
    conn = db.get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM channels WHERE id = ?", (channel_id,))
    channel = cursor.fetchone()
    
    if not channel:
        conn.close()
        raise HTTPException(404, "채널을 찾을 수 없습니다.")

    # 2. 토큰 저장 경로 설정 (tokens/channel_{id}.pickle)
    token_dir = os.path.join(config.BASE_DIR, "tokens")
    os.makedirs(token_dir, exist_ok=True)
    token_path = os.path.join(token_dir, f"channel_{channel_id}.pickle")
    
    try:
        # 3. 인증 시작 (기존 서비스 재활용)
        # get_authenticated_service 내부에서 '없으면 새로 인증' 로직이 돔
        # 로컬 브라우저가 열리고 인증 진행
        print(f"[Auth] Starting OAuth for channel {channel_id} ({channel['name']}) -> {token_path}")
        
        # 만약 기존 토큰이 있다면 삭제하여 강제 재인증 유도 (선택 사항)
        # if os.path.exists(token_path):
        #     os.remove(token_path)
            
        youtube_upload_service.get_authenticated_service(token_path=token_path)
        
        # 4. DB에 토큰 경로 업데이트
        cursor.execute("UPDATE channels SET credentials_path = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?", (token_path, channel_id))
        conn.commit()
        conn.close()
        
        return {"status": "success", "message": f"채널 '{channel['name']}' 인증이 완료되었습니다."}
        
    except Exception as e:
        conn.close()
        print(f"[Auth] Failed: {e}")
        raise HTTPException(500, f"인증 실패: {str(e)}")

# ===========================================
# 서버 실행 (Direct Run)
# ===========================================
# ===========================================
# API: 배경음악 생성 (MusicGen)
# ===========================================

# Pydantic 모델
class MusicGenRequest(BaseModel):
    prompt: str
    duration: int = 10  # 5~30초
    project_id: Optional[int] = None

@app.get("/music-gen", response_class=HTMLResponse)
async def music_gen_page(request: Request):
    """배경음악 생성 페이지"""
    return templates.TemplateResponse("pages/music_gen.html", {
        "request": request,
        "page": "music-gen",
        "title": "배경음악 생성"
    })

@app.post("/api/music/generate")
async def generate_background_music(req: MusicGenRequest):
    """MusicGen으로 배경음악 생성"""
    try:
        from services.music_service import music_service
        
        # 프롬프트 검증
        if not req.prompt or len(req.prompt.strip()) < 3:
            raise HTTPException(400, "프롬프트를 입력해주세요 (최소 3자)")
        
        # 길이 검증
        duration = max(5, min(30, req.duration))
        
        # 파일명 생성
        import time
        timestamp = int(time.time())
        filename = f"bgm_{timestamp}.wav"
        
        # 음악 생성
        file_path = await music_service.generate_music(
            prompt=req.prompt,
            duration_seconds=duration,
            filename=filename,
            project_id=req.project_id
        )
        
        # 웹 접근 경로
        rel_path = os.path.relpath(file_path, config.OUTPUT_DIR)
        web_url = f"/output/{rel_path}".replace("\\", "/")
        
        # DB에 저장 (선택사항)
        if req.project_id:
            db.update_project_setting(req.project_id, 'background_music_path', file_path)
        
        return {
            "status": "ok",
            "path": file_path,
            "url": web_url,
            "duration": duration,
            "prompt": req.prompt
        }
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"Music generation error: {e}")
        raise HTTPException(500, f"음악 생성 중 오류가 발생했습니다: {str(e)}")
if __name__ == "__main__":
    import uvicorn


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

@app.post("/api/video/upload-external/{project_id}")
async def upload_external_video(project_id: int, file: UploadFile = File(...)):
    """외부 영상 파일 업로드"""
    try:
        # 파일 확장자 검증
        allowed_extensions = ['.mp4', '.mov', '.avi', '.mkv', '.webm']
        file_ext = os.path.splitext(file.filename)[1].lower()
        
        if file_ext not in allowed_extensions:
            raise HTTPException(400, f"지원하지 않는 파일 형식입니다. {', '.join(allowed_extensions)} 파일만 업로드 가능합니다.")
        
        # 파일 크기 검증 (2GB)
        max_size = 2 * 1024 * 1024 * 1024
        file.file.seek(0, 2)  # 파일 끝으로 이동
        file_size = file.file.tell()
        file.file.seek(0)  # 파일 처음으로 되돌리기
        
        if file_size > max_size:
            raise HTTPException(400, "파일 크기가 너무 큽니다. 최대 2GB까지 업로드 가능합니다.")
        
        # 저장 경로 생성
        upload_dir = os.path.join(config.OUTPUT_DIR, "external", str(project_id))
        os.makedirs(upload_dir, exist_ok=True)
        
        # 파일 저장
        safe_filename = f"external_video{file_ext}"
        file_path = os.path.join(upload_dir, safe_filename)
        
        with open(file_path, "wb") as f:
            content = await file.read()
            f.write(content)
        
        # 웹 접근 경로
        rel_path = os.path.relpath(file_path, config.OUTPUT_DIR)
        web_url = f"/output/{rel_path}".replace("\\", "/")
        
        # DB에 저장
        db.update_project_setting(project_id, 'external_video_path', file_path)
        
        return {
            "status": "ok",
            "path": file_path,
            "url": web_url,
            "size": file_size,
            "filename": file.filename
        }
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"External video upload error: {e}")
        raise HTTPException(500, f"업로드 중 오류가 발생했습니다: {str(e)}")


@app.delete("/api/video/delete-external/{project_id}")
async def delete_external_video(project_id: int):
    """업로드된 외부 영상 삭제"""
    try:
        # DB에서 경로 조회
        settings = db.get_project_settings(project_id)
        if not settings or not settings.get('external_video_path'):
            raise HTTPException(404, "업로드된 영상이 없습니다.")
        
        file_path = settings['external_video_path']
        
        # 파일 삭제
        if os.path.exists(file_path):
            os.remove(file_path)
        
        # DB에서 경로 제거
        db.update_project_setting(project_id, 'external_video_path', None)
        
        return {"status": "ok"}
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"External video delete error: {e}")
        raise HTTPException(500, f"삭제 중 오류가 발생했습니다: {str(e)}")


@app.post("/api/youtube/upload-external/{project_id}")
async def upload_external_to_youtube(project_id: int):
    """업로드된 외부 영상을 YouTube에 게시"""
    try:
        # 프로젝트 정보 조회
        project = db.get_project(project_id)
        if not project:
            raise HTTPException(404, "프로젝트를 찾을 수 없습니다.")
        
        # 외부 영상 경로 조회
        settings = db.get_project_settings(project_id)
        if not settings or not settings.get('external_video_path'):
            raise HTTPException(404, "업로드된 영상이 없습니다.")
        
        video_path = settings['external_video_path']
        
        if not os.path.exists(video_path):
            raise HTTPException(404, "영상 파일을 찾을 수 없습니다.")
        
        # YouTube 업로드 서비스 import
        from services.youtube_upload_service import youtube_upload_service
        
        # 메타데이터 조회 (title, description, tags)
        metadata = db.get_metadata(project_id)
        title = metadata.get('titles', [project['name']])[0] if metadata else project['name']
        description = metadata.get('description', '') if metadata else ''
        tags = metadata.get('tags', []) if metadata else []
        
        # YouTube 업로드
        result = await youtube_upload_service.upload_video(
            video_path=video_path,
            title=title,
            description=description,
            tags=tags,
            category_id="22",  # People & Blogs
            privacy_status="private"  # 기본값: 비공개
        )
        
        if result.get('status') == 'ok':
            video_id = result.get('video_id')
            
            # DB에 YouTube 비디오 ID 저장
            db.update_project_setting(project_id, 'youtube_video_id', video_id)
            db.update_project_setting(project_id, 'is_published', 1)
            
            return {
                "status": "ok",
                "video_id": video_id,
                "url": f"https://www.youtube.com/watch?v={video_id}"
            }
        else:
            raise HTTPException(500, result.get('error', 'YouTube 업로드 실패'))
            
    except HTTPException:
        raise
    except Exception as e:
        print(f"YouTube upload error: {e}")
        raise HTTPException(500, f"YouTube 업로드 중 오류가 발생했습니다: {str(e)}")



if __name__ == "__main__":
    print("=" * 50)
    print("🚀 피카디리스튜디오 v2.0 시작")
    print("=" * 50)

    config.validate()
    
    # Initialize & Migrate Database
    db.init_db()
    db.migrate_db()



    now_kst = config.get_kst_time()
    print(f"📍 서버 시간(KST): {now_kst.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"📍 서버: http://{config.HOST}:{config.PORT}")
    print("=" * 50)

    uvicorn.run(
        "main:app",
        host=config.HOST,
        port=config.PORT,
        reload=config.DEBUG
    )
