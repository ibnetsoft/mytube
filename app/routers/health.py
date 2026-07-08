from fastapi import APIRouter
from config import config

router = APIRouter()

@router.get("/api/health")
async def health_check():
    """서버 상태 및 API 연결 확인"""
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
