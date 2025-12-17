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
from typing import List, Optional, Dict, Any
import uvicorn
import os
import httpx
import asyncio
import json
import re
import datetime
from pathlib import Path

from config import config
import database as db
from services.gemini_service import gemini_service

# FastAPI 앱 생성
app = FastAPI(
    title="wingsAIStudio",
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

class GeminiRequest(BaseModel):
    prompt: str
    temperature: float = 0.7
    max_tokens: int = 8192

class TTSRequest(BaseModel):
    text: str
    provider: str = "gtts"  # elevenlabs, google_cloud, gtts, gemini
    voice_id: Optional[str] = None
    language: str = "ko-KR"
    style_prompt: Optional[str] = None
    project_id: Optional[int] = None

class VideoRequest(BaseModel):
    script: str
    image_prompts: List[str]
    voice_id: Optional[str] = None
    style: str = "default"

class ProjectCreate(BaseModel):
    name: str
    topic: Optional[str] = None

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
    """모든 프로젝트 목록"""
    return {"projects": db.get_all_projects()}

@app.post("/api/projects")
async def create_project(req: ProjectCreate):
    """새 프로젝트 생성"""
    project_id = db.create_project(req.name, req.topic)
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
    db.delete_project(project_id)
    return {"status": "ok"}

# 프로젝트 데이터 저장 엔드포인트
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
                aspect_ratio="9:16",
                num_images=1
            )
            
            if images:
                # 이미지 저장
                filename = f"p{project_id}_s{p['scene_number']}_{int(time.time())}.png"
                output_path = os.path.join(config.OUTPUT_DIR, filename)
                
                with open(output_path, "wb") as f:
                    f.write(images[0])
                
                p["image_url"] = f"/output/{filename}"
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
        "key": config.YOUTUBE_API_KEY
    }

    if req.published_after:
        params["publishedAfter"] = req.published_after

    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"{config.YOUTUBE_BASE_URL}/search",
            params=params
        )
        return response.json()


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

class ScriptStructureRequest(BaseModel):
    topic: str
    duration: str
    tone: str
    notes: Optional[str] = None

@app.post("/api/gemini/generate-structure")
async def gemini_generate_structure(req: ScriptStructureRequest):
    """대본 구조 생성 (중복 방지 적용)"""
    """대본 구조 생성 (중복 방지 적용)"""
    try:
        # 1. 최근 프로젝트 조회
        recent_projects = db.get_recent_projects(limit=5)
        recent_titles = [p['name'] for p in recent_projects]

        # 2. 분석 데이터 구성 (단순화)
        # Gemini가 숫자를 시간으로 인식하도록 단위 추가
        duration_str = f"{req.duration}초" if req.duration.isdigit() else req.duration

        analysis_data = {
            "topic": req.topic,
            "duration_category": duration_str,
            "tone": req.tone,
            "user_notes": req.notes
        }

        # 3. Gemini 호출
        result = await gemini_service.generate_script_structure(analysis_data, recent_titles)
        
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

@app.post("/api/gemini/analyze-comments")
async def gemini_analyze_comments(req: AnalysisRequest):
    """비디오 종합 분석 (댓글 + 메타데이터)"""
    # 1. 댓글 가져오기
    comments_data = await youtube_comments(req.video_id, 50) # 상위 50개만
    
    comments = []
    if "items" in comments_data:
        for item in comments_data["items"]:
            snippet = item["snippet"].get("topLevelComment", {}).get("snippet", {})
            text = snippet.get("textDisplay", "")
            if text:
                comments.append(text)

    # 댓글이 없어도 메타데이터 분석은 가능하도록 진행 (단, 경고 포함)
    comments_text = chr(10).join(comments[:30]) if comments else "댓글 없음 (비활성화되었거나 데이터 부족)"

    # 2. Gemini로 종합 분석
    prompt = f"""당신은 100만 유튜버 컨설턴트입니다.
다음 유튜브 영상의 데이터를 분석하여 '성공 요인'과 '벤치마킹 포인트'를 도출해주세요.

[영상 정보]
- 제목: {req.title}
- 채널: {req.channel_title}
- 조회수: {req.view_count:,}회
- 좋아요: {req.like_count:,}개
- 게시일: {req.published_at[:10]}
- 태그: {', '.join(req.tags[:10])}
- 설명(요약): {req.description[:200]}...

[시청자 반응(댓글)]
{comments_text}

다음 내용을 포함하여 JSON으로 분석해주세요:
1. sentiment: 긍정/부정/중립 비율
2. success_factors: 이 영상이 조회수가 잘 나온 이유 (제목 어그로, 썸네일, 소재 선정 등 다각도 분석)
3. main_topics: 영상 및 댓글에서 다루는 주요 주제
4. viewer_needs: 댓글에서 파악되는 시청자들의 니즈나 불만
5. content_suggestions: 이 영상을 벤치마킹하여 만들 수 있는 콘텐츠 아이디어
6. summary: 종합 요약

JSON 포맷:
{{
    "sentiment": {{"positive": 70, "negative": 10, "neutral": 20}},
    "success_factors": ["요인1", "요인2", "요인3"],
    "main_topics": ["주제1", "주제2"],
    "viewer_needs": ["니즈1", "니즈2"],
    "content_suggestions": ["제안1", "제안2"],
    "summary": "요약 텍스트"
}}

JSON만 반환하세요."""

    result = await gemini_generate(GeminiRequest(prompt=prompt, temperature=0.4))

    if result["status"] == "ok":
        # JSON 파싱
        json_match = re.search(r'\{[\s\S]*\}', result["text"])
        if json_match:
            try:
                analysis = json.loads(json_match.group())
                return {"status": "ok", "analysis": analysis, "comment_count": len(comments)}
            except:
                pass
    
    return {"status": "error", "error": "분석 결과를 파싱할 수 없습니다"}


# ===========================================
# API: TTS
# ===========================================

@app.post("/api/tts/generate")
async def tts_generate(req: TTSRequest):
    """TTS 음성 생성"""
    import time
    from services.tts_service import tts_service

    now_kst = config.get_kst_time()
    filename = f"tts_{now_kst.strftime('%Y%m%d_%H%M%S')}.mp3"

    try:
        # 1. ElevenLabs
        if req.provider == "elevenlabs":
            output_path = await tts_service.generate_elevenlabs(
                text=req.text,
                voice_id=req.voice_id,
                filename=filename
            )
            
        # 2. Google Cloud TTS
        elif req.provider == "google_cloud":
            # voice_id가 없으면 기본값 사용
            voice = req.voice_id or "ko-KR-Neural2-A"
            output_path = await tts_service.generate_google_cloud(
                text=req.text,
                voice_name=voice,
                filename=filename
            )

        # 3. gTTS (기본값/무료)
        elif req.provider == "gtts":
            output_path = await tts_service.generate_gtts(
                text=req.text,
                filename=filename
            )

        # 4. Gemini (New)
        elif req.provider == "gemini":
            output_path = await tts_service.generate_gemini(
                text=req.text,
                voice_name=req.voice_id or "Puck",
                language_code=req.language or "ko-KR",
                style_prompt=req.style_prompt,
                filename=filename
            )
            
        else:
            raise HTTPException(400, f"지원하지 않는 TTS 제공자: {req.provider}")

        # DB 저장 (프로젝트와 연결)
        if req.project_id:
             try:
                 # /output/filename.mp3 -> 절대 경로 변환 필요 없음 (save_tts에서 처리하거나, URL만 저장하거나)
                 # db.save_tts(project_id, service, voice, audio_path)
                 # audio_path는 절대 경로임.
                 db.save_tts(
                     project_id=req.project_id,
                     service=req.provider,
                     voice=req.voice_id or "default",
                     audio_path=output_path
                 )
             except Exception as db_e:
                 print(f"TTS DB 저장 실패: {db_e}")

        return {
            "status": "ok",
            "file": filename,
            "url": f"/output/{filename}",
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

@app.post("/api/image/generate")
async def generate_image(req: ImageGenerateRequest):
    """Gemini Imagen 3로 이미지 생성"""
    if not config.GEMINI_API_KEY:
        raise HTTPException(400, "Gemini API 키가 설정되지 않았습니다")

    try:
        from google import genai

        client = genai.Client(api_key=config.GEMINI_API_KEY)

        # 이미지 생성
        response = client.models.generate_images(
            model="imagen-3.0-generate-002",
            prompt=req.prompt,
            config={
                "number_of_images": 1,
                "aspect_ratio": req.aspect_ratio,
                "safety_filter_level": "BLOCK_MEDIUM_AND_ABOVE"
            }
        )

        # 이미지 저장
        import time
        filename = f"thumbnail_{int(time.time())}.png"
        output_path = os.path.join(config.OUTPUT_DIR, filename)

        if response.generated_images:
            response.generated_images[0].image.save(output_path)
            return {
                "status": "ok",
                "file": filename,
                "url": f"/output/{filename}"
            }
        else:
            return {"status": "error", "error": "이미지 생성 실패"}

    except Exception as e:
        return {"status": "error", "error": str(e)}


class ThumbnailGenerateRequest(BaseModel):
    prompt: str
    text: str
    text_position: str = "center"  # top, center, bottom
    text_color: str = "#FFFFFF"
    font_size: int = 72

@app.post("/api/image/generate-thumbnail")
async def generate_thumbnail(req: ThumbnailGenerateRequest):
    """썸네일 생성 (이미지 + 텍스트 합성)"""
    if not config.GEMINI_API_KEY:
        raise HTTPException(400, "Gemini API 키가 설정되지 않았습니다")

    try:
        from google import genai
        from PIL import Image, ImageDraw, ImageFont
        import io

        client = genai.Client(api_key=config.GEMINI_API_KEY)

        # 1. Imagen 3로 배경 이미지 생성
        response = client.models.generate_images(
            model="imagen-3.0-generate-002",
            prompt=req.prompt + ", YouTube thumbnail background, high quality, 1280x720",
            config={
                "number_of_images": 1,
                "aspect_ratio": "16:9",
                "safety_filter_level": "BLOCK_MEDIUM_AND_ABOVE"
            }
        )

        if not response.generated_images:
            return {"status": "error", "error": "배경 이미지 생성 실패"}

        # 2. 이미지 로드
        img_data = response.generated_images[0].image._pil_image
        img = img_data.resize((1280, 720), Image.LANCZOS)

        # 3. 텍스트 오버레이
        draw = ImageDraw.Draw(img)

        # 폰트 설정 (시스템 폰트 사용)
        try:
            # Windows 한글 폰트
            font = ImageFont.truetype("malgun.ttf", req.font_size)
        except:
            try:
                font = ImageFont.truetype("arial.ttf", req.font_size)
            except:
                font = ImageFont.load_default()

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
        output_path = os.path.join(config.OUTPUT_DIR, filename)
        img.save(output_path, "PNG", quality=95)

        return {
            "status": "ok",
            "file": filename,
            "url": f"/output/{filename}"
        }

    except Exception as e:
        return {"status": "error", "error": str(e)}


@app.post("/api/image/generate-prompts")
async def generate_image_prompts(script: str, style: str = "realistic", count: int = 5):
    """대본 기반 이미지 프롬프트 생성"""
    prompt = f"""당신은 AI 이미지 생성 프롬프트 전문가입니다.
아래 대본을 읽고, 영상에 사용할 이미지 프롬프트를 생성해주세요.

[대본]
{script[:2000]}

[스타일]
{style}

[요청]
- {count}개의 이미지 프롬프트를 생성하세요
- 각 프롬프트는 영어로 작성하세요
- Midjourney/DALL-E에 적합한 형식으로 작성하세요

JSON 형식으로 반환:
{{
    "prompts": [
        {{"scene": "장면 설명 (한국어)", "prompt": "영어 프롬프트", "style_tags": "--ar 16:9 --v 6"}}
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
    style: str = Body("realistic")
):
    """이미지를 생성하고 저장"""
    try:
        # 이미지 생성 (Gemini Imagen)
        images_bytes = await gemini_service.generate_image(
            prompt=prompt,
            num_images=1,
            aspect_ratio="16:9"
        )

        if not images_bytes:
            return {"status": "error", "error": "이미지가 생성되지 않았습니다."}
        
        # 파일 저장 경로 설정
        project_dir = STATIC_DIR / "images" / str(project_id)
        project_dir.mkdir(parents=True, exist_ok=True)
        
        filename = f"scene_{scene_number}_{int(datetime.datetime.now().timestamp())}.png"
        filepath = project_dir / filename
        
        # 파일 저장
        with open(filepath, "wb") as f:
            f.write(images_bytes[0])
            
        image_url = f"/static/images/{project_id}/{filename}"
        
        # DB 업데이트 (이미지 URL 저장)
        # 기존 프롬프트 레코드가 있다면 업데이트, 없다면 새로 생성 (여기서는 간단히 프롬프트 테이블 업데이트 로직 생략하고 URL 반환에 집중)
        # 실제로는 image_prompts 테이블의 image_url 컬럼을 업데이트해야 함.
        # MVP: 클라이언트가 받아서 DB 업데이트 요청을 보낼 수도 있고, 서버에서 바로 처리할 수도 있음.
        # 여기서는 서버에서 처리하는 것이 자동화에 유리함.
        
        try:
            conn = db.get_db()
            cursor = conn.cursor()
            # 해당 프로젝트, 씬 번호에 맞는 레코드가 있는지 확인
            cursor.execute(
                "SELECT id FROM image_prompts WHERE project_id = ? AND scene_number = ?",
                (project_id, scene_number)
            )
            row = cursor.fetchone()
            
            if row:
                cursor.execute(
                    "UPDATE image_prompts SET image_url = ?, prompt_en = ? WHERE id = ?",
                    (image_url, prompt, row['id'])
                )
            else:
                # 레코드가 없다면 새로 생성 (프롬프트 생성 단계를 건너뛰었을 경우 등)
                cursor.execute(
                    "INSERT INTO image_prompts (project_id, scene_number, prompt_en, image_url) VALUES (?, ?, ?, ?)",
                    (project_id, scene_number, prompt, image_url)
                )
            conn.commit()
            conn.close()
        except Exception as e:
            print(f"DB Update Error: {e}")

        return {"status": "ok", "image_url": image_url}

    except Exception as e:
        print(f"Image Generation Error: {e}")
        return {"status": "error", "error": str(e)}


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


@app.post("/api/projects/{project_id}/render")
async def render_project_video(
    project_id: int,
    background_tasks: BackgroundTasks,
    use_subtitles: bool = True
):
    """프로젝트 영상 최종 렌더링 (이미지 + 오디오 + 자막)"""
    
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

    # 2. 백그라운드 렌더링 시작
    from services.video_service import video_service
    
    now_kst = config.get_kst_time()
    output_filename = f"final_{project_id}_{now_kst.strftime('%Y%m%d_%H%M%S')}.mp4"
    
    async def process_project_render():
        try:
            # A. 기본 영상 생성 (이미지 + 오디오)
            # 이미지당 지속 시간은 오디오 길이 / 이미지 수
            from moviepy.editor import AudioFileClip
            audio_clip = AudioFileClip(audio_path)
            audio_duration = audio_clip.duration
            audio_clip.close()
            
            duration_per_image = audio_duration / len(images)
            
            video_path = video_service.create_slideshow(
                images=images,
                audio_path=audio_path,
                output_filename=f"temp_{output_filename}",
                duration_per_image=duration_per_image
            )
            
            final_path = video_path
            
            # B. 자막 생성 및 합성
            if use_subtitles and script_data and script_data.get("full_script"):
                script = script_data["full_script"]
                
                # 자막 데이터 생성 (단순 등분할)
                subs = video_service.generate_simple_subtitles(script, audio_duration)
                
                if subs:
                    # 자막 합성
                    final_path = video_service.add_subtitles(
                        video_path=video_path,
                        subtitles=subs,
                        output_filename=output_filename
                    )
                    
                    # 임시 파일 삭제
                    try:
                        os.remove(video_path)
                    except:
                        pass

            # C. DB 업데이트
            db.update_project_setting(project_id, "video_path", f"/output/{os.path.basename(final_path)}")
            db.update_project(project_id, status="rendered")
            print(f"프로젝트 {project_id} 렌더링 완료: {final_path}")

        except Exception as e:
            print(f"프로젝트 {project_id} 렌더링 실패: {e}")
            import traceback
            traceback.print_exc()

    background_tasks.add_task(process_project_render)

    return {
        "status": "processing",
        "message": "최종 영상 렌더링이 시작되었습니다.",
        "output_file": output_filename
    }


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

(Generated by wingsAIStudio)
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
# 서버 시작
# ===========================================

if __name__ == "__main__":
    import uvicorn

    print("=" * 50)
    print("🚀 wingsAIStudio v2.0 시작")
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
