"""
wingsAIStudio - FastAPI 메인 서버
YouTube 영상 자동화 제작 플랫폼 (Python 기반)
"""
from fastapi import FastAPI, HTTPException, BackgroundTasks, Query, Body, Request, Form
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
    subtitle_font_size: Optional[int] = None


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
async def save_analysis(project_id: int, req: AnalysisSave):
    """분석 결과 저장"""
    db.save_analysis(project_id, req.video_data, req.analysis_result)
    db.update_project(project_id, status="analyzed")
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

    # 3. 이미지 일괄 생성 (Imagen 3)
    generated_prompts = []
    import time
    
    # BackgroundTasks로 돌리면 좋겠지만 현재는 동기적으로 처리 (사용자 경험 고려)
    for p in prompts:
        try:
            # 영어 프롬프트 사용
            images = await gemini_service.generate_image(
                prompt=p["prompt_en"],
                aspect_ratio="16:9",
                num_images=1
            )
            
            if images:
                # 프로젝트별 폴더 경로 가져오기
                output_dir, web_dir = get_project_output_dir(project_id)

                # 이미지 저장
                filename = f"p{project_id}_s{p['scene_number']}_{int(time.time())}.png"
                output_path = os.path.join(output_dir, filename)
                
                with open(output_path, "wb") as f:
                    f.write(images[0])
                
                # 웹 경로 업데이트
                p["image_url"] = f"{web_dir}/{filename}"
        except Exception as e:
            print(f"이미지 생성 실패 (Scene {p.get('scene_number')}): {e}")
            p["image_url"] = ""  # 실패 시 빈 문자열
            
        generated_prompts.append(p)

    # 4. DB 저장
    db.save_image_prompts(project_id, generated_prompts)

    return {"status": "ok", "prompts": generated_prompts}


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
    if key in ['duration_seconds', 'is_uploaded']:
        value = int(value)
    result = db.update_project_setting(project_id, key, value)
    if not result:
        raise HTTPException(400, f"유효하지 않은 설정 키: {key}")
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
    topic: str
    duration: int = 60
    tone: str = "informative"
    notes: Optional[str] = None
    target_language: Optional[str] = "ko"

@app.post("/api/gemini/generate-structure")
async def generate_script_structure_api(req: StructureGenerateRequest):
    """대본 구조 생성 (중복 방지 적용)"""
    try:
        # 1. 최근 프로젝트 조회
        recent_projects = db.get_recent_projects(limit=5)
        recent_titles = [p['name'] for p in recent_projects]

        # 2. 분석 데이터 구성 (단순화)
        # Gemini가 숫자를 시간으로 인식하도록 단위 추가
        duration_str = f"{req.duration}초"

        analysis_data = {
            "topic": req.topic,
            "duration_category": duration_str,
            "tone": req.tone,
            "user_notes": req.notes
        }

        # 3. Gemini 호출
        # [MODIFIED] target_language 전달
        result = await gemini_service.generate_script_structure(
            analysis_data, 
            recent_titles, 
            target_language=req.target_language
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
        result_filename = os.path.join(output_dir, filename)
    else:
        # Fallback
        web_dir = "/output"
        result_filename = filename # tts_service 내부에서 OUTPUT_DIR과 결합

        # ----------------------------------------------------------------
    try:
        # ----------------------------------------------------------------
        # 멀티 보이스 모드 처리
        # ----------------------------------------------------------------
        if req.multi_voice and req.voice_map:
            # 1. 텍스트 파싱 (Frontend와 동일한 로직: "이름: 대사")
            segments = []
            lines = req.text.split('\n')
            
            # 정규식: "이름: 대사"
            pattern = re.compile(r'^([^\s:\[\]\(\)]+)(?:\(.*\))?[:](.+)')
            
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

            # 2. 세그먼트별 오디오 생성
            audio_files = []
            
            # 기본 목소리 (req.voice_id)를 'default' 화자용으로 사용하거나 fallback
            default_voice = req.voice_id
            
            for idx, seg in enumerate(segments):
                seg_speaker = seg["speaker"]
                seg_text = seg["text"]
                if not seg_text: continue
                
                # 화자별 보이스 매핑 확인 (없으면 기본 voice_id 사용)
                target_voice = req.voice_map.get(seg_speaker, default_voice)
                
                # 임시 파일명
                seg_filename = f"{base_filename}_seg_{idx}.{ext}"
                if req.project_id:
                    seg_path = os.path.join(output_dir, seg_filename)
                else:
                    seg_path = seg_filename # tts_service가 알아서 처리 (주의: 중복 방지 위해 절대경로 권장)
                    # 위 get_project_output_dir 로직 참고: project_id 없으면 OUTPUT_DIR 기준 상대경로일 수 있음
                    # 안전하게 절대경로로 변환
                    seg_path = os.path.join(config.OUTPUT_DIR, seg_filename)

                # 개별 생성 호출 (Gemini만 지원한다고 가정하거나, provider 따름)
                # 여기서는 provider 파라미터를 그대로 사용
                try:
                    # Generate call reuse
                    # tts_service 호출을 위해 직접 함수 매핑
                    if req.provider == "gemini":
                        await tts_service.generate_gemini(
                            seg_text, target_voice, req.language, req.style_prompt, seg_path
                        )
                    elif req.provider == "google_cloud":
                        await tts_service.generate_google_cloud(
                            seg_text, target_voice, req.language, seg_path, req.speed
                        )
                    # ElevenLabs 등 추가 가능
                    else:
                        # Fallback to Gemini if complex parsing is needed? No, just use requested provider
                         await tts_service.generate_gemini(
                            seg_text, target_voice, req.language, req.style_prompt, seg_path, req.speed
                        )
                    
                    audio_files.append(seg_path)
                    
                    # Rate Limit 방지
                    await asyncio.sleep(0.5) 
                    
                except Exception as e:
                    print(f"Segment generation failed: {e}")
                    # 실패 시 무시하거나 에러 처리? 일단 진행
            
            # 3. 오디오 합치기 (MoviePy 사용)
            if audio_files:
                from moviepy.editor import AudioFileClip, concatenate_audioclips
                
                clips = []
                for af in audio_files:
                    try:
                        clips.append(AudioFileClip(af))
                    except:
                        pass
                
                if clips:
                    final_clip = concatenate_audioclips(clips)
                    final_clip.write_audiofile(result_filename)
                    final_clip.close()
                    for clip in clips: clip.close()
                    
                    # 임시 파일 삭제 (선택사항 - 디버깅 위해 남길수도 있지만 삭제 권장)
                    # for af in audio_files: os.remove(af)
                    
                    output_path = result_filename
                else:
                     return {"status": "error", "error": "생성된 오디오 세그먼트가 없습니다."}
            else:
                 return {"status": "error", "error": "파싱된 대본 세그먼트가 없습니다."}

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


class ThumbnailGenerateRequest(BaseModel):
    prompt: str
    text: str
    text_position: str = "center"
    text_color: str = "#FFFFFF"
    font_size: int = 72
    language: str = "ko" # 언어 설정 추가

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

        client = genai.Client(api_key=config.GEMINI_API_KEY)

        # 1. Imagen 3로 배경 이미지 생성
        response = client.models.generate_images(
            model="imagen-4.0-generate-001",
            prompt=req.prompt + ", YouTube thumbnail background, high quality, 1280x720",
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
        draw = ImageDraw.Draw(img)

        # 폰트 설정 (다국어 지원)
        font = None
        system = platform.system()
        
        if system == 'Windows':
            try:
                if req.language == 'ja':
                    # 일본어: 메이리오 or MS 고딕
                    try: font = ImageFont.truetype("meiryo.ttc", req.font_size)
                    except: font = ImageFont.truetype("msgothic.ttc", req.font_size)
                elif req.language == 'en':
                     font = ImageFont.truetype("arial.ttf", req.font_size)
                else: 
                     # 한국어/기본: 맑은 고딕
                     font = ImageFont.truetype("malgun.ttf", req.font_size)
            except:
                # 폰트 로드 실패 시 fallback
                font = ImageFont.load_default()
        
        # 폰트가 여전히 없으면(리눅스 등) 기본값
        if font is None:
             try: font = ImageFont.truetype("malgun.ttf", req.font_size)
             except: font = ImageFont.load_default()

        # 텍스트 위치 계산
        bbox = draw.textbbox((0, 0), req.text, font=font)
        text_width = bbox[2] - bbox[0]
        text_height = bbox[3] - bbox[1]

        x = (1280 - text_width) // 2

        if req.text_position == "top":
            y = 50
        elif req.text_position == "bottom":
            y = 720 - text_height - 50
        else:  # center
            y = (720 - text_height) // 2

        # 텍스트 그림자 (가독성)
        shadow_offset = 3
        draw.text((x + shadow_offset, y + shadow_offset), req.text, font=font, fill="#000000")
        draw.text((x, y), req.text, font=font, fill=req.text_color)

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
        print(f"Thumbnail generation error: {e}")
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






@app.post("/api/image/generate-prompts")
async def generate_image_prompts(script: str, style: str = "realistic", count: int = 0):
    """대본 기반 이미지 프롬프트 생성"""
    
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
{script[:3000]}

[스타일 지침]
"{detailed_style}"
모든 이미지 프롬프트에 위 스타일 키워드를 반드시 포함시켜야 합니다.

[요청]
{count_instruction}
- 각 프롬프트는 영어로 작성하세요
- Midjourney/DALL-E에 적합한 형식으로 작성하세요
- 프롬프트 시작 부분에 스타일 키워드를 배치하세요.

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
            raise HTTPException(400, "유효한 이미지 파일이 없습니다.")
            
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

        def render_executor_func(target_dir_arg, use_subtitles_arg, target_resolution_arg):
            # 몽키패치: MoviePy 구버전 호환성 해결
            import PIL.Image
            if not hasattr(PIL.Image, 'ANTIALIAS'):
                PIL.Image.ANTIALIAS = PIL.Image.LANCZOS

            try:
                with open("c:/Users/kimse/Downloads/유튜브소재발굴기/롱폼생성기/debug_v2.log", "a", encoding="utf-8") as rf:
                    rf.write(f"[{datetime.datetime.now()}] Starting render V2 for project {project_id}\n")
                    rf.write(f"[{datetime.datetime.now()}] Images: {len(images)}, Audio: {audio_path}\n")


                # A. 기본 영상 생성 (이미지 + 오디오)
                with open("c:/Users/kimse/Downloads/유튜브소재발굴기/롱폼생성기/debug_v2.log", "a", encoding="utf-8") as rf:
                    rf.write(f"[{datetime.datetime.now()}] Importing moviepy...\n")
                
                # 이미지당 지속 시간은 오디오 길이 / 이미지 수
                from moviepy.editor import AudioFileClip
                
                with open("c:/Users/kimse/Downloads/유튜브소재발굴기/롱폼생성기/debug_v2.log", "a", encoding="utf-8") as rf:
                    rf.write(f"[{datetime.datetime.now()}] Loading audio clip...\n")
                    
                audio_clip = AudioFileClip(audio_path)
                audio_duration = audio_clip.duration
                audio_clip.close()
                
                with open("c:/Users/kimse/Downloads/유튜브소재발굴기/롱폼생성기/debug_v2.log", "a", encoding="utf-8") as rf:
                    rf.write(f"[{datetime.datetime.now()}] Audio duration: {audio_duration}\n")
                
                duration_per_image = audio_duration / len(images)
                
                # temp 파일도 프로젝트 폴더 내에 생성
                temp_filename = f"temp_{final_output_filename}"
                temp_path = os.path.join(target_dir_arg, temp_filename)
                
                # 프로젝트 정보 조회 (제목용)
                project_info = db.get_project(project_id)
                project_title = project_info['name'] if project_info else ""

                with open("c:/Users/kimse/Downloads/유튜브소재발굴기/롱폼생성기/debug_v2.log", "a", encoding="utf-8") as rf:
                    rf.write(f"[{datetime.datetime.now()}] Calling create_slideshow...\n")

                video_path = video_service.create_slideshow(
                    images=images,
                    audio_path=audio_path,
                    output_filename=temp_path,
                    duration_per_image=duration_per_image,
                    resolution=target_resolution_arg, # Use arg
                    title_text="", # 사용자 요청: 프로젝트명 고정 노출 제거
                    project_id=project_id # For progress tracking
                )
                
                final_path = video_path
                
                # B. 자막 생성 및 합성
                if use_subtitles_arg: # Use arg
                    # script 변수 안전하게 가져오기
                    script = ""
                    if script_data and script_data.get("full_script"):
                        script = script_data["full_script"]
                    
                    # 자막 데이터 확인 (우선순위: 편집된 JSON > VTT > AI Align)
                    subs = []
                    
                    # 1. 편집된 자막 JSON 로드
                    inner_output_dir, _ = get_project_output_dir(project_id)
                    saved_sub_path = os.path.join(inner_output_dir, f"subtitles_{project_id}.json")
                    
                    if os.path.exists(saved_sub_path):
                        import json
                        with open(saved_sub_path, "r", encoding="utf-8") as f:
                            subs = json.load(f)
                            print(f"DEBUG: 편집된 자막 JSON 사용 ({len(subs)} lines)")

                    # 2. VTT 파일 (Edge TTS) 로드
                    elif os.path.exists(audio_path.replace(".mp3", ".vtt").replace(".wav", ".vtt")):
                        vtt_path = audio_path.replace(".mp3", ".vtt").replace(".wav", ".vtt")
                        print(f"DEBUG: VTT 자막 파일 발견 -> {vtt_path}")
                        
                        # VTT 파싱 (간단 구현)
                        # TODO: webvtt-py 라이브러리 사용 권장
                        try:
                            with open(vtt_path, "r", encoding="utf-8") as f:
                                lines = f.readlines()
                            
                            current_sub = {}
                            for line in lines:
                                line = line.strip()
                                if "-->" in line:
                                    start, end = line.split(" --> ")
                                    # VTT time format: 00:00:05.123
                                    def parse_time(t_str):
                                        parts = t_str.split(":")
                                        if len(parts) == 3:
                                            h, m, s = parts
                                            return int(h)*3600 + int(m)*60 + float(s)
                                        elif len(parts) == 2:
                                            m, s = parts
                                            return int(m)*60 + float(s)
                                        return 0.0
                                    
                                    current_sub["start"] = parse_time(start)
                                    current_sub["end"] = parse_time(end)
                                elif line and not line.startswith("WEBVTT") and not line.isdigit() and "-->" not in line:
                                    current_sub["text"] = line
                                    if "start" in current_sub:
                                        subs.append(current_sub)
                                        current_sub = {}
                        except Exception as e:
                            print(f"VTT Parsing Error: {e}")
                            
                    # 3. Fallback: AI 자막 생성 (Faster-Whisper)
                    elif script: # 대본이 있을 때만
                        print("DEBUG: 저장된 자막 없음. AI 자막 생성 시도...")
                        # ... omitted ...
                        pass
                    

                            
                    # 3. AI Align (Fallback)
                    if not subs:
                        subs = video_service.generate_aligned_subtitles(audio_path, script)
                        print(f"DEBUG: AI Align 자막 사용 ({len(subs)} lines)")
                    
                    if subs:
                        # 자막 스타일 설정 로드
                        settings = db.get_project_settings(project_id)
                        font = settings.get("subtitle_font", "malgun.ttf")
                        color = settings.get("subtitle_color", "white")
                        style_name = settings.get("subtitle_style_enum", "Basic_White")
                        font_size = settings.get("subtitle_font_size", 80)
                        
                        # 자막 합성
                        final_path = video_service.add_subtitles(
                            video_path=video_path,
                            subtitles=subs,
                            output_filename=final_output_path,
                            font=font,
                            font_color=color, # 기존 변수 사용
                            font_size=font_size, # DB 값 사용
                            style_name=style_name
                        )
                        
                        # 임시 파일 삭제
                    try:
                        if os.path.exists(video_path) and video_path != final_path:
                            os.remove(video_path)
                    except:
                        pass

                # C. DB 업데이트
                # 웹 경로: /output/Project_Date/video.mp4
                web_video_path = f"{web_dir}/{os.path.basename(final_path)}"
                db.update_project_setting(project_id, "video_path", web_video_path)
                db.update_project(project_id, status="rendered")
                print(f"프로젝트 {project_id} 렌더링 완료: {final_path}")

            except Exception as e:
                import traceback
                error_msg = f"프로젝트 렌더링 실패: {e}"
                print(error_msg)
                traceback.print_exc()
                
                try:
                    with open("c:/Users/kimse/Downloads/유튜브소재발굴기/롱폼생성기/debug_v2.log", "a", encoding="utf-8") as rf:
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
        background_tasks.add_task(render_executor_func, target_dir_arg=output_dir, use_subtitles_arg=request.use_subtitles, target_resolution_arg=target_resolution)

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
        except Exception:
            pass

    # 2. Edge TTS로 생성된 VTT가 있으면 폴백 (우선순위 2)
    if not subtitles and os.path.exists(vtt_path):
        import webvtt
        try:
            # webvtt 라이브러리가 없다면 간단 파싱 폴백
            for caption in webvtt.read(vtt_path):
                subtitles.append({
                    "start": caption.start_in_seconds,
                    "end": caption.end_in_seconds,
                    "text": caption.text
                })
        except ImportError:
            # Simple VTT Parser (생략 - 필요시 구현)
            pass
            
            
    # 오디오 Web URL 계산
    # audio_path가 absolute path일 때, config.OUTPUT_DIR에 대한 상대 경로 계산
    # 예: C:/.../output/Project_2024/tts.mp3 -> /output/Project_2024/tts.mp3
    try:
        rel_path = os.path.relpath(audio_path, config.OUTPUT_DIR)
        audio_url = f"/output/{rel_path}".replace("\\", "/")
    except ValueError:
        # 경로가 다른 드라이브에 있거나 파악 불가 시
        audio_url = f"/output/{os.path.basename(audio_path)}"

    # [FIX] 이미지 리스트 조회 (자막 매칭용)
    images = []
    try:
        prompts = db.get_image_prompts(project_id)
        # scene_number 순으로 정렬 보장
        prompts.sort(key=lambda x: x.get('scene_number', 0))
        images = [p['image_url'] for p in prompts if p.get('image_url')]
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
        font_name = "malgun.ttf" # 기본값

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
                    font_color="white", # Style dictates this usually
                    font_name=font_name,
                    style_name=style_enum,
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
# 서버 시작
# ===========================================

if __name__ == "__main__":
    import uvicorn

    print("=" * 50)
    print("🚀 피카디리스튜디오 v2.0 시작")
    print("=" * 50)

    config.validate()



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
