from pydantic import BaseModel
from typing import List, Optional, Dict

class WebtoonScene(BaseModel):
    scene_number: int
    character: str
    dialogue: str
    visual_desc: str
    image_path: str
    original_image_path: Optional[str] = None
    voice_id: Optional[str] = None
    atmosphere: Optional[str] = None
    sound_effects: Optional[str] = None
    focal_point_y: Optional[float] = 0.5
    engine_override: Optional[str] = None
    effect_override: Optional[str] = None
    motion_desc: Optional[str] = None
    voice_settings: Optional[dict] = None
    audio_direction: Optional[dict] = None

class ScanRequest(BaseModel):
    path: str

class AnalyzeDirRequest(BaseModel):
    project_id: int
    files: List[str]
    psd_exclude_layer: Optional[str] = None

class WebtoonAutomateRequest(BaseModel):
    project_id: int
    scenes: List[WebtoonScene]
    use_lipsync: bool = True
    use_subtitles: bool = True
    character_map: Optional[dict] = None

class WebtoonPlanRequest(BaseModel):
    project_id: int
    scenes: List[dict]

class LocalImageRequest(BaseModel):
    file_path: str

class WebtoonSingleSceneRequest(BaseModel):
    project_id: int
    scene_index: int
    scene: WebtoonScene
