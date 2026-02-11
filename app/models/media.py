"""
Media Pydantic Models (Image, Video, TTS, Search)
"""

from pydantic import BaseModel
from typing import Optional, List, Dict


class SearchRequest(BaseModel):
    query: str
    max_results: int = 10
    order: str = "relevance"
    published_after: Optional[str] = None
    video_duration: Optional[str] = None
    relevance_language: Optional[str] = None


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


class PromptsGenerateRequest(BaseModel):
    script: str
    style: str = "realistic"
    count: int = 0
    character_reference: Optional[str] = None
    project_id: Optional[int] = None
