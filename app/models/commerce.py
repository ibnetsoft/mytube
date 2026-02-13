from typing import Optional, List
from pydantic import BaseModel

class ProductAnalysisRequest(BaseModel):
    product_url: str

class CommerceVideoRequest(BaseModel):
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
    engine: str = "topview"

class StylePreset(BaseModel):
    key: str
    name: str
    description: str
    model_default: str
    background_default: str
