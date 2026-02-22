from fastapi import APIRouter, HTTPException, Body, BackgroundTasks
from typing import List, Optional, Dict
import os
import database as db
import config
from app.models.media import SearchRequest, GeminiRequest, TTSRequest, PromptsGenerateRequest
from services import gemini_service, tts_service, replicate_service

router = APIRouter(prefix="/api/media", tags=["Media"])

@router.post("/gemini-generate")
async def gemini_generate_api(req: GeminiRequest):
    try:
        result = await gemini_service.generate_text(req.prompt, req.temperature, req.max_tokens)
        return {"status": "success", "result": result}
    except Exception as e:
        raise HTTPException(500, str(e))

@router.post("/tts-generate")
async def tts_generate_api(req: TTSRequest):
    try:
        # tts_service에서 처리
        audio_path = await tts_service.generate_audio(
            text=req.text,
            voice_id=req.voice_id,
            provider=req.provider,
            project_id=req.project_id,
            language=req.language,
            speed=req.speed
        )
        return {"status": "success", "audio_url": f"/outputs/{os.path.basename(audio_path)}"}
    except Exception as e:
        raise HTTPException(500, str(e))

@router.post("/image-generate-prompts")
async def generate_image_prompts(req: PromptsGenerateRequest):
    try:
        prompts = await gemini_service.generate_image_prompts(req.script, req.style, req.count)
        return {"status": "success", "prompts": prompts}
    except Exception as e:
        raise HTTPException(500, str(e))

@router.post("/image-generate")
async def generate_image_api(prompt: str = Body(..., embed=True), style: str = "realistic"):
    try:
        # replicate_service 또는 다른 서비스 이용
        image_url = await replicate_service.generate_image(prompt, style)
        return {"status": "success", "image_url": image_url}
    except Exception as e:
        raise HTTPException(500, str(e))

from fastapi import Query
from fastapi.responses import FileResponse

@router.get("/view")
@router.get("/v")
async def view_media(path: str = Query(...)):
    """로컬 파일 경로를 받아 스트리밍/다운로드 (이미지/영상 미리보기용)"""
    if not os.path.exists(path):
        raise HTTPException(404, f"File not found: {path}")
    return FileResponse(path)
