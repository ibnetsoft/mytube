from pydantic import BaseModel
from typing import List, Optional, Dict, Any, Union

class AutoPilotStartRequest(BaseModel):
    keyword: Optional[str] = None
    topic: Optional[str] = None
    preset_id: Optional[int] = None
    mode: str = "longform"
    image_style: str = "realistic"
    thumbnail_style: str = "face"
    video_scene_count: int = 10
    all_video: bool = False
    motion_method: str = "standard"
    script_style: str = "story"
    voice_provider: str = "elevenlabs"
    voice_id: str = "default"
    duration_minutes: int = 10
    duration_seconds: Optional[int] = None
    subtitle_settings: Optional[dict] = None

class AutopilotPresetSave(BaseModel):
    name: str
    settings: dict
