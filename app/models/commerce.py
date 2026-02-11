"""
커머스 쇼츠 Pydantic 모델
"""

from pydantic import BaseModel
from typing import Optional, List


class ProductAnalysisRequest(BaseModel):
    """제품 분석 요청"""
    product_url: str


class CommerceVideoRequest(BaseModel):
    """커머스 영상 생성 요청"""
    product_url: str
    product_name: Optional[str] = None
    product_price: Optional[str] = None
    product_description: Optional[str] = None
    product_images: Optional[List[str]] = []
    style_preset: str = "electronics"
    model_type: Optional[str] = None
    background_type: Optional[str] = None
    music_type: Optional[str] = None
    message: Optional[str] = None
    cta: str = "buy_now"


class StylePreset(BaseModel):
    """스타일 프리셋"""
    key: str
    name: str
    description: str
    model_default: str
    background_default: str
