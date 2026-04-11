"""
Gemini API 라우터
/api/gemini/* 및 /api/nursery/* 엔드포인트
"""
from fastapi import APIRouter
from pydantic import BaseModel
from typing import Optional, List
import httpx

import database as db
from config import config
from app.models.media import GeminiRequest
from services.gemini_service import gemini_service

router = APIRouter(tags=["Gemini"])


class StructureGenerateRequest(BaseModel):
    project_id: Optional[int] = None
    topic: str
    duration: int = 60
    tone: str = "informative"
    notes: Optional[str] = None
    target_language: Optional[str] = "ko"
    script_style: Optional[str] = "story"
    mode: str = "monologue"


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


class NurseryDevelopRequest(BaseModel):
    title: str
    summary: str
    project_id: Optional[int] = None


class NurseryImagePromptsRequest(BaseModel):
    title: str
    lyrics: str
    project_id: Optional[int] = None


@router.post("/api/gemini/generate-structure")
async def generate_script_structure_api(req: StructureGenerateRequest):
    """대본 구조 생성 (중복 방지 적용)"""
    try:
        recent_projects = db.get_recent_projects(limit=5)
        recent_titles = [p['name'] for p in recent_projects]

        from services.settings_service import settings_service
        all_settings = settings_service.get_settings()
        style_prompts = all_settings.get("script_styles", {})
        style_prompt = style_prompts.get(req.script_style, "")

        if not style_prompt and req.script_style:
            style_label = req.script_style.replace('_', ' ').title()
            style_prompt = f"Write the script in '{style_label}' style. Adapt tone, pacing, and narrative structure to match this genre/format."

        db_analysis = None
        if req.project_id:
            db_analysis = db.get_analysis(req.project_id)

        duration_str = f"{req.duration}초"

        analysis_data = {
            "topic": req.topic,
            "duration_category": duration_str,
            "tone": req.tone,
            "user_notes": req.notes,
            "script_style": req.script_style,
            "success_analysis": db_analysis.get("analysis_result") if db_analysis else None
        }

        accumulated_knowledge = db.get_recent_knowledge(limit=10, script_style=req.script_style)

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


@router.post("/api/gemini/deep-dive")
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


@router.post("/api/gemini/generate")
async def gemini_generate(req: GeminiRequest):
    """Gemini 텍스트 생성"""
    print(f"🔍 [Gemini API] Request received for prompt: {req.prompt[:100]}...")
    url = f"{config.GEMINI_URL}?key={config.GEMINI_API_KEY}"

    payload = {
        "contents": [{"parts": [{"text": req.prompt}]}],
        "generationConfig": {
            "temperature": req.temperature,
            "maxOutputTokens": req.max_tokens
        }
    }

    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.post(url, json=payload)
            try:
                result = response.json()
            except Exception:
                return {"status": "error", "error": f"API 응답 파싱 실패 (HTTP {response.status_code}): {response.text[:200]}"}

            if "candidates" in result:
                try:
                    text = result["candidates"][0]["content"]["parts"][0]["text"]
                    return {"status": "ok", "text": text}
                except (KeyError, IndexError) as e:
                    return {"status": "error", "error": f"응답 구조 오류: {str(e)}. Raw: {str(result)[:200]}"}
            else:
                # 에러 상세 메시지 추출
                err_msg = result.get("error", {})
                if isinstance(err_msg, dict):
                    err_msg = err_msg.get("message", str(err_msg))
                return {"status": "error", "error": str(err_msg)[:300]}
    except httpx.TimeoutException:
        return {"status": "error", "error": "Gemini API 요청 시간 초과 (120초). 다시 시도해주세요."}
    except Exception as e:
        return {"status": "error", "error": f"Gemini API 호출 실패: {str(e)}"}


@router.post("/api/gemini/analyze-comments")
async def gemini_analyze_comments(req: AnalysisRequest):
    """비디오 종합 분석 (댓글 + 자막)"""
    # 1. 댓글 가져오기
    params = {
        "part": "snippet",
        "videoId": req.video_id,
        "maxResults": 50,
        "order": "relevance",
        "key": config.YOUTUBE_API_KEY
    }
    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"{config.YOUTUBE_BASE_URL}/commentThreads",
            params=params
        )
        comments_data = response.json()

    comments = []
    if "items" in comments_data:
        for item in comments_data["items"]:
            snippet = item["snippet"].get("topLevelComment", {}).get("snippet", {})
            text = snippet.get("textDisplay", "")
            if text:
                comments.append(text)

    # 2. Gemini 분석
    try:
        analysis = await gemini_service.analyze_comments(
            comments=comments,
            video_title=req.title,
            transcript=req.transcript
        )

        if "error" in analysis:
            return {"status": "error", "error": analysis["error"]}

        return {"status": "ok", "analysis": analysis, "comment_count": len(comments)}

    except Exception as e:
        print(f"분석 실패: {e}")
        return {"status": "error", "error": str(e)}


# --- Nursery Rhyme (동요) 전용 엔드포인트 ---

@router.get("/api/nursery/ideas")
async def get_nursery_ideas():
    """동요 아이디어 10개 생성"""
    try:
        ideas = await gemini_service.generate_nursery_rhyme_ideas()
        return {"status": "ok", "ideas": ideas}
    except Exception as e:
        return {"status": "error", "error": str(e)}


@router.post("/api/nursery/develop")
async def develop_nursery_song_api(req: NurseryDevelopRequest):
    """아이디어를 기반으로 동요 가사 및 구성 개발"""
    try:
        result = await gemini_service.develop_nursery_song(req.title, req.summary)
        if not result:
            return {"status": "error", "error": "노래 생성 실패"}
        return {"status": "ok", "result": result}
    except Exception as e:
        return {"status": "error", "error": str(e)}


@router.post("/api/nursery/image-prompts")
async def generate_nursery_image_prompts_api(req: NurseryImagePromptsRequest):
    """가사 기반 3D 애니메이션 스타일 이미지 프롬프트 생성"""
    try:
        scenes = await gemini_service.generate_nursery_image_prompts(req.title, req.lyrics)
        if not scenes:
            return {"status": "error", "error": "이미지 프롬프트 생성 실패"}
        return {"status": "ok", "scenes": scenes}
    except Exception as e:
        return {"status": "error", "error": str(e)}
@router.get("/api/logs")
async def get_ai_logs_api(limit: int = 100):
    """AI 생성 로그 목록 조회"""
    try:
        logs = db.get_ai_logs(limit=limit)
        return {"status": "ok", "logs": logs}
    except Exception as e:
        return {"status": "error", "error": str(e)}

@router.delete("/api/logs")
async def clear_ai_logs_api():
    """AI 생성 로그 초기화"""
    try:
        db.clear_ai_logs()
        return {"status": "ok"}
    except Exception as e:
        return {"status": "error", "error": str(e)}
