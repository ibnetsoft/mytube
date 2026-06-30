"""
숏폼 영상 생성 관련 Pydantic 모델
"""

from pydantic import BaseModel, Field
from typing import Optional, Dict, Any


class ShortsVideoRequest(BaseModel):
    """숏폼 영상 생성 요청 모델"""
    short_index: int = Field(..., description="선택된 쇼츠 인덱스")
    short_data: Dict[str, Any] = Field(..., description="쇼츠 데이터 (title, hook, script 등)")
    video_style: str = Field(default="vlog", description="영상 스타일")

    # TopView AI 모델 설정
    avatar_id: Optional[str] = Field(None, description="아바타 모델 ID")
    voice_id: Optional[str] = Field(None, description="음성 모델 ID")
    background_style: str = Field(default="studio", description="배경 스타일")
    video_length: int = Field(default=30, description="영상 길이 (초)")

    project_id: Optional[int] = Field(None, description="프로젝트 ID")


class ShortsVideoResponse(BaseModel):
    """숏폼 영상 응답 모델"""
    status: str
    video_id: Optional[int] = None
    task_id: Optional[str] = None
    message: Optional[str] = None


class ShortsVideoSettings(BaseModel):
    """숏폼 영상 설정 모델"""
    avatar_id: Optional[str] = None
    voice_id: Optional[str] = None
    background_style: str = "studio"
    video_length: int = 30
    project_id: Optional[int] = None