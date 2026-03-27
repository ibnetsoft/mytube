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
        # 프로젝트가 지정된 경우 캐릭터 정보 + 스타일 설정 로드
        characters = []
        style_key = req.style
        gemini_instruction = ""
        duration_seconds = req.duration_seconds or 300

        if req.project_id:
            characters = db.get_project_characters(req.project_id) or []
            p_settings = db.get_project_settings(req.project_id) or {}
            # DB 저장된 스타일 키 우선 사용
            saved_style = p_settings.get("image_style") or p_settings.get("visual_style")
            if saved_style:
                style_key = saved_style
            if not req.duration_seconds:
                duration_seconds = int(p_settings.get("duration_seconds") or 300)

        # 스타일 프리셋에서 prompt_value / gemini_instruction 로드
        style_presets = db.get_style_presets()
        style_data = style_presets.get(style_key, {})
        style_prompt = style_data.get("prompt_value", style_key)
        gemini_instruction = style_data.get("gemini_instruction", "")

        image_prompts = await gemini_service.generate_image_prompts_from_script(
            script=req.script,
            duration_seconds=duration_seconds,
            style_prompt=style_prompt,
            characters=characters if characters else None,
            target_scene_count=req.count if req.count > 0 else None,
            style_key=style_key,
            gemini_instruction=gemini_instruction,
        )

        # project_id가 있으면 기존 프롬프트 덮어쓰고 DB 저장
        if req.project_id and image_prompts:
            db.save_image_prompts(req.project_id, image_prompts)

        return {
            "status": "success",
            "prompts": image_prompts,
            "character_count": len(characters),
        }
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
