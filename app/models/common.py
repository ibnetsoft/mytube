from pydantic import BaseModel
from typing import List, Optional, Dict, Any, Union

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
    provider: str = "elevenlabs"
    project_id: Optional[int] = None
    language: Optional[str] = "ko-KR"
    style_prompt: Optional[str] = None
    speed: Optional[float] = 1.0
    multi_voice: bool = False
    voice_map: Optional[Dict[str, str]] = {}

class VideoRequest(BaseModel):
    script: str
    image_prompts: List[str]
    voice_id: Optional[str] = None
    style: str = "default"

class ProjectCreate(BaseModel):
    name: str
    topic: Optional[str] = None
    target_language: Optional[str] = "ko"

class StylePreset(BaseModel):
    style_key: str
    prompt_value: str
    image_url: Optional[str] = None

class ProjectUpdate(BaseModel):
    name: Optional[str] = None
    topic: Optional[str] = None
    status: Optional[str] = None

class AnalysisSave(BaseModel):
    video_data: dict
    analysis_result: dict

class ScriptStructureSave(BaseModel):
    hook: str
    sections: List[dict]
    cta: str
    style: str
    duration: int

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

class PromptsGenerateRequest(BaseModel):
    script: str
    style: str = "realistic"
    count: int = 0
    character_reference: Optional[str] = None
    project_id: Optional[int] = None

class ProjectSettingUpdate(BaseModel):
    key: str
    value: Any

class ThumbnailsSave(BaseModel):
    ideas: List[dict]
    texts: List[str]
    full_settings: Optional[dict] = None

class ShortsSave(BaseModel):
    shorts_data: List[dict]

class ProjectSettingsSave(BaseModel):
    title: Optional[str] = None
    thumbnail_text: Optional[str] = None
    # ... (생략된 필드들이 많으나 일단 main.py 기준으로 모두 포함)
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
    image_style: Optional[str] = None
    character_ref_text: Optional[str] = None
    character_ref_image_path: Optional[str] = None
    voice_name: Optional[str] = None
    voice_language: Optional[str] = None
    voice_style_prompt: Optional[str] = None
    voice_provider: Optional[str] = None
    voice_speed: Optional[float] = None
    voice_multi_enabled: Optional[int] = None
    voice_mapping_json: Optional[str] = None
    app_mode: Optional[str] = None
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
    target_language: Optional[str] = None
    youtube_video_id: Optional[str] = None
    is_published: Optional[int] = None
    background_video_url: Optional[str] = None
    script_style: Optional[str] = None
    subtitle_path: Optional[str] = None
    image_timings_path: Optional[str] = None
    timeline_images_path: Optional[str] = None
    image_effects_path: Optional[str] = None
    intro_video_path: Optional[str] = None
    thumbnail_style: Optional[str] = None

class ChannelCreate(BaseModel):
    name: str
    handle: str
    description: Optional[str] = None

class ChannelResponse(BaseModel):
    id: int
    name: str
    handle: str
    description: Optional[str]
    created_at: Any
    credentials_path: Optional[str] = None

class SubtitleDefaultSave(BaseModel):
    subtitle_font: str
    subtitle_font_size: int
    subtitle_color: str
    subtitle_style_enum: str
    subtitle_stroke_color: str
    subtitle_stroke_width: float
