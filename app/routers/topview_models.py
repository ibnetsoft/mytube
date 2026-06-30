"""
TopView AI 모델 관리 API 라우터
TopView API에서 제공하는 아바타, 음성 등의 AI 모델 목록 제공
"""

from fastapi import APIRouter, HTTPException
from services.topview_models_service import topview_models_service


router = APIRouter(prefix="/api/topview", tags=["TopView Models"])


@router.get("/models")
async def get_topview_models():
    """
    TopView API에서 제공하는 AI 모델 목록 조회
    - 아바타 모델 목록
    - 음성 모델 목록
    """
    try:
        models = await topview_models_service.get_available_models()

        return {
            "status": "success",
            "models": models
        }

    except Exception as e:
        raise HTTPException(500, f"모델 목록 조회 실패: {str(e)}")


@router.get("/models/avatars")
async def get_avatar_models():
    """아바타 모델 목록만 조회"""
    try:
        avatars = await topview_models_service.get_avatar_models()

        return {
            "status": "success",
            "avatars": avatars
        }

    except Exception as e:
        raise HTTPException(500, f"아바타 모델 조회 실패: {str(e)}")


@router.get("/models/voices")
async def get_voice_models():
    """음성 모델 목록만 조회"""
    try:
        voices = await topview_models_service.get_voice_models()

        return {
            "status": "success",
            "voices": voices
        }

    except Exception as e:
        raise HTTPException(500, f"음성 모델 조회 실패: {str(e)}")