"""
Project Pydantic Models
"""

from pydantic import BaseModel
from typing import Optional, List, Dict, Any


class ProjectCreate(BaseModel):
    name: str
    topic: Optional[str] = None
    target_language: Optional[str] = "ko"
    app_mode: Optional[str] = "longform"
    
    # 디버그용 필드 추가 (필요시)


class ProjectUpdate(BaseModel):
    name: Optional[str] = None
    topic: Optional[str] = None
    status: Optional[str] = None


class ProjectSettingUpdate(BaseModel):
    key: str
    value: Any


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
    subtitle_style_enum: Optional[str] = None
    image_style_prompt: Optional[str] = None
    image_style: Optional[str] = None  # For autopilot sync
    character_ref_text: Optional[str] = None
    character_ref_image_path: Optional[str] = None
    voice_name: Optional[str] = None
    voice_language: Optional[str] = None
    voice_style_prompt: Optional[str] = None
    voice_provider: Optional[str] = None
    voice_speed: Optional[float] = None
    multi_voice: Optional[bool] = None
    
    # Subtitle specific
    subtitle_font: Optional[str] = None
    subtitle_color: Optional[str] = None
    subtitle_font_size: Optional[float] = None
    subtitle_stroke_color: Optional[str] = None
    subtitle_stroke_width: Optional[float] = None
    subtitle_position_y: Optional[str] = None
    subtitle_base_color: Optional[str] = None
    subtitle_pos_y: Optional[str] = None
    subtitle_pos_x: Optional[str] = None
    subtitle_bg_enabled: Optional[int] = None
    subtitle_stroke_enabled: Optional[int] = None
    subtitle_line_spacing: Optional[float] = None
    subtitle_bg_color: Optional[str] = None
    subtitle_bg_opacity: Optional[float] = None
    
    # Project status
    target_language: Optional[str] = None
    youtube_video_id: Optional[str] = None
    is_published: Optional[int] = None
    background_video_url: Optional[str] = None
    script_style: Optional[str] = None
    
    # Paths
    subtitle_path: Optional[str] = None
    image_timings_path: Optional[str] = None
    timeline_images_path: Optional[str] = None
    image_effects_path: Optional[str] = None
    intro_video_path: Optional[str] = None
    
    # Thumbnail
    thumbnail_style: Optional[str] = None


class StylePreset(BaseModel):
    style_key: str
    prompt_value: str
    image_url: Optional[str] = None


class AnalysisSave(BaseModel):
    video_data: dict
    analysis_result: dict


class ScriptStructureSave(BaseModel):
    hook: str
    sections: List[dict]
    cta: str
    style: str
    duration: int
    count: Optional[int] = None      # 숏츠 개수


class ScriptSave(BaseModel):
    full_script: str
    word_count: int
    estimated_duration: int


class ImagePromptsSave(BaseModel):
    prompts: List[dict]


class MetadataSave(BaseModel):
    titles: List[str] = []
    description: Optional[str] = ""
    tags: List[str] = []
    hashtags: List[str] = []


class ThumbnailsSave(BaseModel):
    ideas: List[dict]
    texts: List[str]
    full_settings: Optional[dict] = None


class ShortsSave(BaseModel):
    shorts_data: List[dict]


class SubtitleDefaultSave(BaseModel):
    subtitle_font: str
    subtitle_font_size: int
    subtitle_color: str
    subtitle_style_enum: str
    subtitle_stroke_color: str
    subtitle_stroke_width: float
