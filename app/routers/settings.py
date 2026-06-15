from fastapi import APIRouter, HTTPException, UploadFile, File, Form, Body
from pydantic import BaseModel
from typing import Optional, Dict, Any
import database as db
import os
import shutil
import uuid
import time
import httpx
from fastapi.responses import RedirectResponse, HTMLResponse
from config import config
from app.modes import DEFAULT_APP_MODE, normalize_app_mode

router = APIRouter(prefix="/api/settings", tags=["Settings"])


STANDARD_MEMBERSHIPS = {"std", "standard"}


def _is_standard_member() -> bool:
    try:
        from services.auth_service import auth_service
        return (auth_service.get_membership() or "std").lower() in STANDARD_MEMBERSHIPS
    except Exception:
        return True


def _require_advanced_settings_access():
    if _is_standard_member():
        raise HTTPException(status_code=403, detail="Standard mode can only access basic settings.")


ADVANCED_GLOBAL_SETTING_FIELDS = {
    "gemini_tts",
    "script_styles",
    "webtoon_auto_split",
    "webtoon_smart_pan",
    "webtoon_convert_zoom",
    "webtoon_plan_prompt",
    "webtoon_vertical_prompt",
    "webtoon_horizontal_prompt",
    "webtoon_motion_pan",
    "webtoon_motion_zoom",
    "webtoon_motion_action",
    "video_engine",
    "veo_model_version",
    "blog_client_id",
    "blog_client_secret",
    "blog_id",
    "wp_url",
    "wp_username",
    "wp_password",
    "youtube_api_key",
    "gemini_api_key",
    "elevenlabs_api_key",
    "pexels_api_key",
    "replicate_api_token",
    "openai_api_key",
}

class GlobalSettings(BaseModel):
    app_mode: Optional[str] = None
    gemini_tts: Optional[Dict[str, Any]] = None
    script_styles: Optional[Dict[str, Any]] = None
    # [NEW] Webtoon Settings
    webtoon_auto_split: Optional[bool] = None
    webtoon_smart_pan: Optional[bool] = None
    webtoon_convert_zoom: Optional[bool] = None
    webtoon_plan_prompt: Optional[str] = None
    webtoon_vertical_prompt: Optional[str] = None
    webtoon_horizontal_prompt: Optional[str] = None
    webtoon_motion_pan: Optional[str] = None
    webtoon_motion_zoom: Optional[str] = None
    webtoon_motion_action: Optional[str] = None
    video_engine: Optional[str] = None # 'veo' or 'replicate'
    veo_model_version: Optional[str] = None
    # [NEW] Blog Settings
    blog_client_id: Optional[str] = None
    blog_client_secret: Optional[str] = None
    blog_id: Optional[str] = None
    # [NEW] WordPress Settings
    wp_url: Optional[str] = None
    wp_username: Optional[str] = None
    wp_password: Optional[str] = None
    # [NEW] User Info
    user_name: Optional[str] = None
    user_nationality: Optional[str] = None
    user_phone: Optional[str] = None
    user_email: Optional[str] = None
    # [NEW] API Keys
    youtube_api_key: Optional[str] = None
    gemini_api_key: Optional[str] = None
    elevenlabs_api_key: Optional[str] = None
    pexels_api_key: Optional[str] = None
    replicate_api_token: Optional[str] = None
    openai_api_key: Optional[str] = None
    # [NEW] Google Drive Settings
    use_external_render: Optional[bool] = None
    drive_render_queue_path: Optional[str] = None
    drive_path_ko: Optional[str] = None
    drive_path_en: Optional[str] = None
    drive_path_ja: Optional[str] = None
    drive_active_lang: Optional[str] = None

@router.get("")
async def get_global_settings_api():
    """글로벌 설정 조회 (Project 1 + Global Table)"""
    # 1. Load Global Table Settings
    global_conf = {
        "app_mode": db.get_global_setting("app_mode", None), # Use None to allow fallback
        "gemini_tts": db.get_global_setting("gemini_tts", {}),
        "script_styles": db.get_global_setting("script_styles", {}),
        "template_image_url": db.get_global_setting("template_image_url"),
        # [NEW] Webtoon
        "webtoon_auto_split": db.get_global_setting("webtoon_auto_split", True, value_type="bool"),
        "webtoon_smart_pan": db.get_global_setting("webtoon_smart_pan", True, value_type="bool"),
        "webtoon_convert_zoom": db.get_global_setting("webtoon_convert_zoom", True, value_type="bool"),
        "webtoon_plan_prompt": db.get_global_setting("webtoon_plan_prompt", ""),
        "webtoon_vertical_prompt": db.get_global_setting("webtoon_vertical_prompt", ""),
        "webtoon_horizontal_prompt": db.get_global_setting("webtoon_horizontal_prompt", ""),
        "webtoon_motion_pan": db.get_global_setting("webtoon_motion_pan", ""),
        "webtoon_motion_zoom": db.get_global_setting("webtoon_motion_zoom", ""),
        "webtoon_motion_action": db.get_global_setting("webtoon_motion_action", ""),
        "video_engine": db.get_global_setting("video_engine", "veo"),
        "veo_model_version": db.get_global_setting("veo_model_version", "veo-3.1-fast-generate-preview"),
        # [NEW] Blog
        "blog_client_id": db.get_global_setting("blog_client_id", ""),
        "blog_client_secret": db.get_global_setting("blog_client_secret", ""),
        "blog_id": db.get_global_setting("blog_id", ""),
        # [NEW] WordPress
        "wp_url": db.get_global_setting("wp_url", ""),
        "wp_username": db.get_global_setting("wp_username", ""),
        "wp_password": db.get_global_setting("wp_password", ""),
        # [NEW] User Info
        "user_name": db.get_global_setting("user_name", ""),
        "user_nationality": db.get_global_setting("user_nationality", ""),
        "user_phone": db.get_global_setting("user_phone", ""),
        "user_email": db.get_global_setting("user_email", ""),
        # [NEW] Google Drive Settings
        "use_external_render": db.get_global_setting("use_external_render", config.USE_EXTERNAL_RENDER, value_type="bool"),
        "drive_render_queue_path": db.get_global_setting("drive_render_queue_path", config.DRIVE_RENDER_QUEUE_PATH),
        "drive_path_ko": db.get_global_setting("drive_path_ko", config.DRIVE_PATH_KO),
        "drive_path_en": db.get_global_setting("drive_path_en", config.DRIVE_PATH_EN),
        "drive_path_ja": db.get_global_setting("drive_path_ja", config.DRIVE_PATH_JA),
        "drive_active_lang": db.get_global_setting("drive_active_lang", config.DRIVE_ACTIVE_LANG)
    }
    
    # 2. Load Default Settings (stored in Project 1 by convention)
    default_project_settings = db.get_project_settings(1) or {}
    
    # 3. Merge (Project 1 is base, Global Table overrides specific keys)
    # But for app_mode, we want Global Table value if exists, else Project 1
    merged = default_project_settings.copy()
    
    # Update only non-None values from global_conf or specific logic
    if global_conf["app_mode"]:
        merged["app_mode"] = normalize_app_mode(global_conf["app_mode"])
    else:
        merged["app_mode"] = normalize_app_mode(merged.get("app_mode"))
    
    # gemini_tts and others from global table are strictly structure objects
    # Autopilot expects flat fields like voice_provider, so we keep Project 1 values
    # unless we want to map gemini_tts back to flat fields. 
    # For now, just returning merged allows Autopilot to find 'voice_provider' from Project 1.
    
    merged["gemini_tts"] = global_conf["gemini_tts"]
    merged["script_styles"] = global_conf["script_styles"]
    merged["template_image_url"] = global_conf["template_image_url"]

    # [NEW] Webtoon
    merged["webtoon_auto_split"] = global_conf["webtoon_auto_split"]
    merged["webtoon_smart_pan"] = global_conf["webtoon_smart_pan"]
    merged["webtoon_convert_zoom"] = global_conf["webtoon_convert_zoom"]
    merged["webtoon_plan_prompt"] = global_conf["webtoon_plan_prompt"]
    merged["webtoon_vertical_prompt"] = global_conf["webtoon_vertical_prompt"]
    merged["webtoon_horizontal_prompt"] = global_conf["webtoon_horizontal_prompt"]
    merged["webtoon_motion_pan"] = global_conf["webtoon_motion_pan"]
    merged["webtoon_motion_zoom"] = global_conf["webtoon_motion_zoom"]
    merged["webtoon_motion_action"] = global_conf["webtoon_motion_action"]
    merged["video_engine"] = global_conf["video_engine"]
    merged["veo_model_version"] = global_conf["veo_model_version"]
    merged["blog_client_id"] = global_conf["blog_client_id"]
    merged["blog_client_secret"] = global_conf["blog_client_secret"]
    merged["blog_id"] = global_conf["blog_id"]
    merged["wp_url"] = global_conf["wp_url"]
    merged["wp_username"] = global_conf["wp_username"]
    merged["wp_password"] = global_conf["wp_password"]
    from services.auth_service import auth_service
    merged["user_name"] = auth_service.get_user_name() or global_conf["user_name"]
    merged["user_nationality"] = auth_service.get_user_nationality() or global_conf["user_nationality"]
    merged["user_phone"] = auth_service.get_user_contact() or global_conf["user_phone"]
    merged["user_email"] = auth_service.get_user_email() or global_conf["user_email"]
    
    merged["use_external_render"] = global_conf["use_external_render"]
    merged["drive_render_queue_path"] = global_conf["drive_render_queue_path"]
    merged["drive_path_ko"] = global_conf["drive_path_ko"]
    merged["drive_path_en"] = global_conf["drive_path_en"]
    merged["drive_path_ja"] = global_conf["drive_path_ja"]
    merged["drive_active_lang"] = global_conf["drive_active_lang"]
    
    # [NEW] Add Current API Keys Status
    api_status = config.get_api_keys_status()
    merged["api_status"] = api_status
    
    return merged

@router.post("")
async def save_global_settings_api(settings: GlobalSettings):
    """글로벌 설정 저장"""
    if _is_standard_member():
        sent_advanced = [
            key for key in ADVANCED_GLOBAL_SETTING_FIELDS
            if getattr(settings, key, None) is not None
        ]
        if sent_advanced:
            raise HTTPException(status_code=403, detail="Standard mode can only save basic settings.")

    # 이전 모드 저장 (모드 변경 감지용)
    previous_mode = normalize_app_mode(db.get_global_setting("app_mode", DEFAULT_APP_MODE))
    
    if settings.app_mode:
        settings.app_mode = normalize_app_mode(settings.app_mode)
        db.save_global_setting("app_mode", settings.app_mode)
        # 템플릿 전역 변수 즉시 업데이트
        from services import app_state
        app_state.switch_mode(settings.app_mode)
    if settings.gemini_tts:
        db.save_global_setting("gemini_tts", settings.gemini_tts)
    if settings.script_styles:
        db.save_global_setting("script_styles", settings.script_styles)

    # [NEW] Webtoon Save
    if settings.webtoon_auto_split is not None:
        db.save_global_setting("webtoon_auto_split", settings.webtoon_auto_split)
    if settings.webtoon_smart_pan is not None:
        db.save_global_setting("webtoon_smart_pan", settings.webtoon_smart_pan)
    if settings.webtoon_convert_zoom is not None:
        db.save_global_setting("webtoon_convert_zoom", settings.webtoon_convert_zoom)
    if settings.webtoon_plan_prompt is not None:
        db.save_global_setting("webtoon_plan_prompt", settings.webtoon_plan_prompt)
    if settings.webtoon_vertical_prompt is not None:
        db.save_global_setting("webtoon_vertical_prompt", settings.webtoon_vertical_prompt)
    if settings.webtoon_horizontal_prompt is not None:
        db.save_global_setting("webtoon_horizontal_prompt", settings.webtoon_horizontal_prompt)
    if settings.webtoon_motion_pan is not None:
        db.save_global_setting("webtoon_motion_pan", settings.webtoon_motion_pan)
    if settings.webtoon_motion_zoom is not None:
        db.save_global_setting("webtoon_motion_zoom", settings.webtoon_motion_zoom)
    if settings.webtoon_motion_action is not None:
        db.save_global_setting("webtoon_motion_action", settings.webtoon_motion_action)
    if settings.video_engine is not None:
        db.save_global_setting("video_engine", settings.video_engine)
    if settings.veo_model_version is not None:
        db.save_global_setting("veo_model_version", settings.veo_model_version)
    if settings.blog_client_id is not None:
        db.save_global_setting("blog_client_id", settings.blog_client_id)
    if settings.blog_client_secret is not None:
        db.save_global_setting("blog_client_secret", settings.blog_client_secret)
    if settings.blog_id is not None:
        db.save_global_setting("blog_id", settings.blog_id)
    if settings.wp_url is not None:
        db.save_global_setting("wp_url", settings.wp_url)
    if settings.wp_username is not None:
        db.save_global_setting("wp_username", settings.wp_username)
    if settings.wp_password is not None:
        db.save_global_setting("wp_password", settings.wp_password)
    # [NEW] User Info
    if settings.user_name is not None:
        db.save_global_setting("user_name", settings.user_name)
    if settings.user_nationality is not None:
        db.save_global_setting("user_nationality", settings.user_nationality)
    if settings.user_phone is not None:
        db.save_global_setting("user_phone", settings.user_phone)
    if settings.user_email is not None:
        db.save_global_setting("user_email", settings.user_email)
    
    # [NEW] Sync to SaaS server (값이 있을 때만 전송)
    from services.auth_service import auth_service
    if settings.user_name is not None or settings.user_nationality is not None or settings.user_phone is not None:
        auth_service.sync_profile(
            name=settings.user_name or "",
            nationality=settings.user_nationality or "",
            contact=settings.user_phone or ""
        )
    
    # [NEW] Update API Keys in config/env
    if settings.youtube_api_key is not None:
        config.update_api_key("YOUTUBE_API_KEY", settings.youtube_api_key)
    if settings.gemini_api_key is not None:
        config.update_api_key("GEMINI_API_KEY", settings.gemini_api_key)
    if settings.elevenlabs_api_key is not None:
        config.update_api_key("ELEVENLABS_API_KEY", settings.elevenlabs_api_key)
    if settings.pexels_api_key is not None:
        config.update_api_key("PEXELS_API_KEY", settings.pexels_api_key)
    if settings.replicate_api_token is not None:
        config.update_api_key("REPLICATE_API_TOKEN", settings.replicate_api_token)
    if settings.openai_api_key is not None:
        config.update_api_key("OPENAI_API_KEY", settings.openai_api_key)
        
    # [NEW] Google Drive Settings Save
    if settings.use_external_render is not None:
        db.save_global_setting("use_external_render", settings.use_external_render)
        config.update_api_key("USE_EXTERNAL_RENDER", str(settings.use_external_render).lower())
    if settings.drive_path_ko is not None:
        db.save_global_setting("drive_path_ko", settings.drive_path_ko)
        config.update_api_key("DRIVE_PATH_KO", settings.drive_path_ko)
    if settings.drive_path_en is not None:
        db.save_global_setting("drive_path_en", settings.drive_path_en)
        config.update_api_key("DRIVE_PATH_EN", settings.drive_path_en)
    if settings.drive_path_ja is not None:
        db.save_global_setting("drive_path_ja", settings.drive_path_ja)
        config.update_api_key("DRIVE_PATH_JA", settings.drive_path_ja)
    if settings.drive_active_lang is not None:
        db.save_global_setting("drive_active_lang", settings.drive_active_lang)
        config.update_api_key("DRIVE_ACTIVE_LANG", settings.drive_active_lang)

    # Automatically resolve DRIVE_RENDER_QUEUE_PATH
    active_lang = settings.drive_active_lang or db.get_global_setting("drive_active_lang", "ko")
    resolved_path = ""
    if active_lang == "ko":
        resolved_path = settings.drive_path_ko or db.get_global_setting("drive_path_ko", config.DRIVE_PATH_KO)
    elif active_lang == "en":
        resolved_path = settings.drive_path_en or db.get_global_setting("drive_path_en", config.DRIVE_PATH_EN)
    elif active_lang == "ja":
        resolved_path = settings.drive_path_ja or db.get_global_setting("drive_path_ja", config.DRIVE_PATH_JA)

    if resolved_path:
        db.save_global_setting("drive_render_queue_path", resolved_path)
        config.update_api_key("DRIVE_RENDER_QUEUE_PATH", resolved_path)
    
    # 모드 변경 여부 반환
    mode_changed = previous_mode != settings.app_mode if settings.app_mode else False
    
    return {
        "status": "ok",
        "mode_changed": mode_changed,
        "previous_mode": previous_mode,
        "new_mode": settings.app_mode
    }

class StylePreset(BaseModel):
    style_key: str
    prompt_value: str
    image_url: Optional[str] = None
    gemini_instruction: Optional[str] = None
    mode: Optional[str] = None  # 'image' | 'blog' | 'all'


def _sync_style_presets_from_supabase_best_effort(require_credentials: bool = False) -> Dict[str, int]:
    """Pull web-admin style presets into local SQLite.

    The desktop platform reads local SQLite, while the web admin writes Supabase.
    Keep this sync best-effort for read paths so the UI still works offline.
    """
    supabase_url = os.getenv("NEXT_PUBLIC_SUPABASE_URL")
    supabase_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
    if not supabase_url or not supabase_key:
        if require_credentials:
            raise HTTPException(status_code=400, detail="Supabase credentials missing on local environment")
        return {"image": 0, "script": 0, "thumbnail": 0}

    try:
        import requests
        import urllib3

        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        headers = {
            "apikey": supabase_key,
            "Authorization": f"Bearer {supabase_key}"
        }
        url = f"{supabase_url.rstrip('/')}/rest/v1/style_presets?select=*"
        r = requests.get(url, headers=headers, timeout=10, verify=False)
        if r.status_code != 200:
            if require_credentials:
                raise HTTPException(status_code=500, detail=f"Supabase request failed: {r.text}")
            print(f"[Preset Sync] Supabase request failed: {r.status_code} {r.text[:200]}")
            return {"image": 0, "script": 0, "thumbnail": 0}

        supabase_presets = r.json()
        image_presets_in_supabase = [p for p in supabase_presets if p.get("preset_type") == "image"]
        if image_presets_in_supabase:
            db.clear_all_style_presets()

        counts = {"image": 0, "script": 0, "thumbnail": 0}
        for preset in supabase_presets:
            ptype = preset.get("preset_type")
            key = preset.get("key_code")
            p_val = preset.get("prompt_template")
            inst = preset.get("gemini_instruction")
            img = preset.get("image_url")
            name_ko = preset.get("display_name_ko")
            name_vi = preset.get("display_name_vi")

            if not key or not p_val:
                continue

            if ptype == "image":
                db.save_style_preset(
                    style_key=key,
                    prompt_value=p_val,
                    image_url=img,
                    gemini_instruction=inst,
                    mode="all",
                    display_name_ko=name_ko,
                    display_name_vi=name_vi
                )
                counts["image"] += 1
            elif ptype == "script":
                db.save_script_style_preset(
                    style_key=key,
                    prompt_value=p_val,
                    display_name_ko=name_ko,
                    display_name_vi=name_vi
                )
                counts["script"] += 1
            elif ptype == "thumbnail":
                db.save_thumbnail_style_preset(
                    style_key=key,
                    prompt_value=p_val,
                    image_url=img,
                    display_name_ko=name_ko,
                    display_name_vi=name_vi
                )
                counts["thumbnail"] += 1

        return counts
    except HTTPException:
        raise
    except Exception as e:
        if require_credentials:
            raise HTTPException(status_code=500, detail=f"Sync error: {str(e)}")
        print(f"[Preset Sync] Failed to pull from Supabase: {e}")
        return {"image": 0, "script": 0, "thumbnail": 0}


# ===========================================
# API: 이미지 스타일 프리셋 관리
# ===========================================

@router.get("/style-presets")
async def get_style_presets_api(mode: Optional[str] = None):
    """이미지 스타일 프리셋 조회. mode=image|blog|all 필터 가능"""
    _sync_style_presets_from_supabase_best_effort()
    presets = db.get_style_presets()

    # Supabase도 없을 때만 하드코딩 fallback 적용
    if not presets:
        default_styles = {
            "realistic": "**[Subject & Atmosphere]**\nA cinematic photorealistic shot of [SUBJECT] in [LOCATION]. The lighting is [LIGHTING_DETAILS] with a [ATMOSPHERE] mood.\n\n**[Environment & Details]**\nDetailed environment featuring [ENVIRONMENT_DETAILS]. High-end textures and sharp details.\n\n**[Camera & Quality]**\n[CAMERA_ANGLE], shot on 35mm lens, f/1.8, 8k resolution, cinematic color grading, ray-traced shadows.",
            "ghibli": "**[Subject & Illustration]**\nA beautiful Studio Ghibli style illustration of [SUBJECT]. They are [ACTION] with detailed expressions.\n\n**[Background & Colors]**\nA scenic background of [LOCATION] during [TIME]. [ARTISTIC_DETAILS], vibrant yet soft color palette, hand-painted aesthetic.\n\n**[Composition & Quality]**\n[CAMERA_ANGLE], clean linework, cinematic anime composition, 4k, crisp focus.",
            "anime": "anime style, vibrant colors, studio ghibli inspired",
            "cinematic": "cinematic lighting, dramatic, movie still, bokeh",
            "cartoon": "cartoon style, cel shading, vibrant, playful",
            "nursery_rhyme": "Cute 3D animation style, Pixar/Disney inspired, vibrant colors, child-friendly environment, no text.",
        }
        for key, val in default_styles.items():
            db.save_style_preset(key, val)
        presets = db.get_style_presets()

    # sports_analysis가 있으면 mode를 'blog'로 설정 (아직 'image'인 경우만)
    if 'sports_analysis' in presets and presets['sports_analysis'].get('mode', 'image') == 'image':
        db.save_style_preset('sports_analysis',
                             presets['sports_analysis']['prompt_value'],
                             mode='blog')
        presets = db.get_style_presets()

    # mode 쿼리 파라미터 필터 적용
    if mode:
        presets = {k: v for k, v in presets.items() if v.get('mode') == mode or v.get('mode') == 'all'}

    return presets

@router.post("/style-presets")
async def save_style_preset_api(preset: StylePreset):
    _require_advanced_settings_access()
    """이미지 스타일 프리셋 저장"""
    db.save_style_preset(preset.style_key, preset.prompt_value, preset.image_url,
                         preset.gemini_instruction, preset.mode)
    return {"status": "ok"}

@router.post("/style-presets/custom")
async def save_custom_style_preset(
    style_key: str = Form(...),
    prompt_value: str = Form(...),
    file: UploadFile = File(None)
):
    _require_advanced_settings_access()
    """커스텀 스타일 저장 (이미지 포함)"""
    image_url = None
    if file:
        try:
            # Sanitize style_key for filename (remove/replace invalid chars)
            safe_key = style_key.replace('/', '_').replace('\\', '_').replace(' ', '_')
            filename = f"style_{safe_key}_{int(time.time())}.png"
            file_path = os.path.join(config.STATIC_DIR, "styles", filename)
            os.makedirs(os.path.dirname(file_path), exist_ok=True)
            
            with open(file_path, "wb") as buffer:
                content = await file.read()
                buffer.write(content)
                
            image_url = f"/static/styles/{filename}"
        except Exception as e:
            raise HTTPException(500, f"이미지 업로드 실패: {e}")

    db.save_style_preset(style_key, prompt_value, image_url)
    return {"status": "ok", "image_url": image_url}

@router.post("/style-presets/analyze")
async def analyze_style_image(
    style_file: Optional[UploadFile] = File(None),
    char_file: Optional[UploadFile] = File(None)
):
    _require_advanced_settings_access()
    """화풍 및 캐릭터 레퍼런스 이미지 통합 분석 (Settings 전용)"""
    from services.auth_service import auth_service
    if not auth_service.check_credits(500):
        # 듀얼 분석은 토큰 소모를 조금 더 높게 잡을 수도 있지만 현재는 동일하게 500 TK
        raise HTTPException(403, "AI 토큰이 부족합니다. (분석 최소 500 TK 필요)")
    
    if not style_file and not char_file:
        raise HTTPException(400, "분석할 이미지를 하나 이상 선택하세요.")

    try:
        from services.gemini_service import gemini_service
        
        prompt = """
        Analyze these two reference images and create a unified visual description for AI image generation.
        
        1. IMAGE A (Style Reference): Analyze the artistic style, color palette, lighting, and texture.
        2. IMAGE B (Character Reference): Analyze the person's identity, face, hair, and unique features.
        
        Task: 
        Generate a "Character Kit Instruction" that tells the image generator to:
        - Maintain the specific identity and appearance from Image B.
        - Apply the exact art style and vibe from Image A.
        - Ensure global consistency for this specific character in this specific style.
        
        Output ONLY the description text. Start with "(Character Kit Guide) ...".
        If only one image is provided, focus on that one.
        """
        
        image_list = []
        if style_file:
            style_bytes = await style_file.read()
            image_list.append(style_bytes)
        if char_file:
            char_bytes = await char_file.read()
            image_list.append(char_bytes)

        # generate_text_from_image가 리스트를 지원하도록 gemini_service에서 처리하거나 여기서 반복문
        # 현재 gemini_service.generate_text_from_image는 단일 이미지만 지원하므로 
        # 여러 이미지를 보낼 수 있는 통합 메서드를 사용하거나 프롬프트에 이미지들을 담아 보냅니다.
        
        # gemini_service.generate_text_from_image를 개선하여 리스트를 받게 하거나, 
        # 직접 모델 호출 (간단하게 하기 위해 gemini_service에 멀티 이미지 지원용 메서드가 있는지 확인 필요)
        # 만약 없다면 gemini_service를 수정하거나 여기서 직접 구현합니다.
        
        description = await gemini_service.generate_text_from_images(prompt, image_list)
        return {"description": description.strip()}
        
    except Exception as e:
        print(f"Analyze dual style image failed: {e}")
        raise HTTPException(500, str(e))

@router.delete("/style-presets/{style_key}")
async def delete_style_preset(style_key: str):
    _require_advanced_settings_access()
    """스타일 프리셋 삭제 (커스텀)"""
    conn = db.get_db()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM style_presets WHERE style_key = ?", (style_key,))
    conn.commit()
    conn.close()
    return {"status": "ok"}


# ===========================================
# API: 대본 스타일 프리셋 관리
# ===========================================

@router.post("/sync-presets")
async def sync_presets_from_supabase():
    _require_advanced_settings_access()
    """Supabase style_presets 테이블로부터 최신 프리셋 데이터를 로컬 SQLite에 동기화"""
    counts = _sync_style_presets_from_supabase_best_effort(require_credentials=True)
    return {
        "status": "ok",
        "message": f"동기화 완료: 이미지 {counts['image']}개, 대본 {counts['script']}개, 썸네일 {counts['thumbnail']}개"
    }

@router.get("/script-style-presets")
async def get_script_style_presets_api(detailed: Optional[bool] = None):
    """모든 대본 스타일 프리셋 조회"""
    if detailed:
        presets = db.get_script_style_presets_detailed()
    else:
        presets = db.get_script_style_presets()
    
    # DB에 하나도 없으면 기본값으로 초기화
    if not presets:
        default_styles = {
            "news": "뉴스 스타일: 객관적이고 신뢰감 있는 톤으로 작성",
            "story": "옛날 이야기 스타일: 구연동화 방식으로 따듯하고 감성적으로 작성",
            "senior_story": "시니어 사연 스타일: 중장년층 공감 사연으로 진솔하고 깊이 있게 작성",
            "script_master": """최종 확정: '딥-다이브' 대본 빌드업 4단계 프로세스 (Ver. 4.0)

[1단계] 대본 정밀 해부 및 흥행 잠재력 진단
임무: 대본을 문장 단위로 정밀 분석하고, '흥행 심리 지도(5070 타겟 제목 리스트)'와 '전문 드라마 기법'을 사용하여 잠재력과 개선점에 대한 '대본 정밀 해부 리포트'를 발행합니다.

실행 원칙:
- [종합 진단] 작품의 가장 매력적인 설정과 개선 필요 지점 명확하게 요약
- [톤앤매너 분석] 나레이션은 시청자에게 정중한 '존댓말' 원칙 (5070 시청자 정서적 유대감)
- [대사 현미경 분석] 감정 설명 대사를 '극적 아이러니(Dramatic Irony)'가 담긴 상황으로 개선
- [장면 구조 분석] 도입부는 '인 미디어스 레스(In medias res)' + '체호프의 총(Chekhov's Gun)' 기법 적용
- [인물 매력도 분석] 주인공에게 '복선(Foreshadowing)'을 통한 숨겨진 능력 암시

[2단계] '감독판 샘플' 제작 및 공동 창작 방향 확정
임무: 지정된 장면을 드라마 기법 + 흥행 코드 + 존댓말 나레이션에 따라 '원본 vs 감독 수정본' 형태로 제공

[3단계] 감독판 대본 전체 집필
임무: 합의된 개선 방향과 스타일을 대본 전체에 일관되게 적용하여 최종 [감독판 대본] 완성

[4단계] 최종 마케팅 에셋 시화
임무: 완성된 대본의 핵심 컨셉을 보여줄 썸네일 비주얼을 구체적으로 묘사"""
        }
        for key, val in default_styles.items():
            db.save_script_style_preset(key, val)
        presets = default_styles
        
    return presets

@router.post("/script-style-presets")
async def save_script_style_preset_api(preset: StylePreset):
    _require_advanced_settings_access()
    """대본 스타일 프리셋 저장"""
    db.save_script_style_preset(preset.style_key, preset.prompt_value)
    return {"status": "ok"}


# ===========================================
# API: 썸네일 스타일 프리셋 관리
# ===========================================

@router.get("/thumbnail-style-presets")
async def get_thumbnail_style_presets_api():
    """모든 썸네일 스타일 프리셋 조회"""
    presets = db.get_thumbnail_style_presets()
    
    # DB에 하나도 없으면 기본값으로 초기화
    if not presets:
        default_styles = {
            "face": "얼굴 강조형: 클로즈업된 인물 얼굴을 중심으로, 강렬한 표정과 시선을 유도하는 구도. 배경은 흐릿하게 처리하고 인물을 부각시킴.",
            "text": "텍스트 중심형: 굵고 가독성 높은 폰트의 텍스트가 중앙을 차지하는 디자인. 배경은 단순하거나 텍스트를 방해하지 않는 패턴 사용.",
            "contrast": "비포/애프터형: 화면을 분할하여 '전(Before)'과 '후(After)'를 명확하게 대비시키는 구도. 색상 대비를 강하게 주어 변화를 강조.",
            "mystery": "미스터리형: 어두운 조명, 실루엣, 물음표 등을 활용하여 호기심을 자극하는 분위기. 중요한 정보는 가려져 있거나 흐릿하게 표현.",
            "minimal": "미니멀형: 여백을 충분히 활용하고, 핵심 요소 1-2개만 배치하여 깔끔하고 세련된 느낌. 색상은 2-3가지로 제한.",
            "dramatic": "드라마틱형: 역동적인 앵글, 강한 명암 대비, 영화 포스터 같은 극적인 연출. 채도가 높고 강렬한 색감 사용.",
            "ghibli": "지브리 감성: 지브리 스튜디오 애니메이션 스타일. 부드러운 수채화풍 배경, 파스텔 톤 색감, 몽환적이고 감성적인 분위기.",
            "k_manhwa": "K만화 스타일: 한국 웹툰/만화 스타일. 굵은 외곽선, 셀 셰이딩, 선명한 플랫 컬러, 애니메이션 캐릭터 디자인, 현대적 한국 만화 미학."
        }
        for key, val in default_styles.items():
            db.save_thumbnail_style_preset(key, val, None) # image_url=None
        
        # Re-fetch formatted
        presets = db.get_thumbnail_style_presets()
        
    return presets

@router.post("/thumbnail-style-presets")
async def save_thumbnail_style_preset_api(preset: StylePreset):
    _require_advanced_settings_access()
    """썸네일 스타일 프리셋 저장"""
    # If preset.image_url is None, db layer will preserve existing if any
    db.save_thumbnail_style_preset(preset.style_key, preset.prompt_value, preset.image_url)
    return {"status": "ok"}

@router.post("/thumbnail-style-presets/custom")
async def add_custom_thumbnail_style_preset(
    style_key: str = Form(...),
    prompt_value: str = Form(...),
    file: UploadFile = File(...)
):
    _require_advanced_settings_access()
    """커스텀 썸네일 스타일 추가 (이미지 포함)"""
    try:
        # Validate file
        if not file.filename:
             raise HTTPException(400, "파일이 없습니다.")

        # Ensure static/img/custom_styles dir exists
        save_dir = os.path.join(config.STATIC_DIR, "img", "custom_styles")
        os.makedirs(save_dir, exist_ok=True)
        
        # Generate filename
        ext = os.path.splitext(file.filename)[1]
        # Sanitize style_key for filename (remove/replace invalid chars)
        safe_key = style_key.replace('/', '_').replace('\\', '_').replace(' ', '_')
        filename = f"thumb_{safe_key}_{uuid.uuid4().hex[:8]}{ext}"
        filepath = os.path.join(save_dir, filename)
        
        # Save file
        with open(filepath, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
            
        # URL path
        image_url = f"/static/img/custom_styles/{filename}"
        
        # Save to DB
        db.save_thumbnail_style_preset(style_key, prompt_value, image_url)
        
        return {"status": "ok", "image_url": image_url}
        
    except Exception as e:
        print(f"Error saving custom thumbnail style: {e}")
        raise HTTPException(500, f"스타일 저장 실패: {str(e)}")

@router.delete("/thumbnail-style-presets/{style_key}")
async def delete_thumbnail_style_preset(style_key: str):
    _require_advanced_settings_access()
    """썸네일 스타일 프리셋 삭제"""
    try:
        conn = db.get_db()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM thumbnail_style_presets WHERE style_key = ?", (style_key,))
        conn.commit()
        conn.close()
        return {"status": "ok"}
    except Exception as e:
        raise HTTPException(500, str(e))

@router.post("/language")
async def set_language(lang: str = Body(..., embed=True)):
    """언어 설정 저장 및 즉시 적용 (ko / en / vi)"""
    allowed = {"ko", "en", "vi"}
    if lang not in allowed:
        raise HTTPException(400, f"지원하지 않는 언어입니다: {lang}. 허용값: {allowed}")
    try:
        # 1. DB 저장
        db.save_global_setting("language", lang)

        # 2. language.pref 파일 저장 (서버 재시작 후 영구 보존)
        try:
            with open("language.pref", "w", encoding="utf-8") as f:
                f.write(lang)
        except Exception as e:
            print(f"[I18N] language.pref write failed: {e}")

        # 3. 실행 중인 translator 즉시 업데이트 (app_state 경유 — circular import 없음)
        try:
            from services import app_state
            success = app_state.switch_language(lang)
            if success:
                print(f"[I18N] Language switched to: {lang} via app_state")
            else:
                print(f"[I18N] app_state not ready yet, will apply on next restart")
        except Exception as e:
            print(f"[I18N] Live translator update failed: {e}")

        return {"status": "ok", "lang": lang}
    except Exception as e:
        raise HTTPException(500, str(e))

@router.get("/autopilot")
async def get_autopilot_settings():
    """오토파일럿 설정 조회"""
    try:
        # 오토파일럿 설정은 관례적으로 프로젝트 ID 1번에 저장되어 있음
        settings = db.get_project_settings(1)
        return {"status": "success", "settings": settings}
    except Exception as e:
        raise HTTPException(500, str(e))

@router.post("/autopilot")
async def save_autopilot_settings(settings: Dict[str, Any] = Body(...)):
    _require_advanced_settings_access()
    """오토파일럿 설정 저장"""
    try:
        db.save_project_settings(1, settings)
        return {"status": "success"}
    except Exception as e:
        raise HTTPException(500, str(e))

# ===========================================
# API: 웹툰 수동 처리 학습 룰 (Learning Rules)
# ===========================================

class WebtoonRuleAdd(BaseModel):
    condition_type: str
    condition_value: str
    action_type: str
    description: str

@router.get("/webtoon-rules")
async def get_webtoon_rules_api():
    try:
        rules = db.get_webtoon_rules()
        return {"status": "success", "rules": rules}
    except Exception as e:
        raise HTTPException(500, str(e))

@router.post("/webtoon-rules")
async def add_webtoon_rule_api(req: WebtoonRuleAdd):
    _require_advanced_settings_access()
    try:
        db.save_webtoon_rule(req.condition_type, req.condition_value, req.action_type, req.description)
        return {"status": "success"}
    except Exception as e:
        raise HTTPException(500, str(e))

@router.delete("/webtoon-rules/{rule_id}")
async def delete_webtoon_rule_api(rule_id: int):
    _require_advanced_settings_access()
    try:
        db.delete_webtoon_rule(rule_id)
        return {"status": "success"}
    except Exception as e:
        raise HTTPException(500, str(e))

@router.post("/crop-grid")
async def crop_grid_image(
    file: UploadFile = File(...),
    panel: int = Form(...) # 1: Top-Left, 2: Top-Right, 3: Bottom-Left, 4: Bottom-Right
):
    _require_advanced_settings_access()
    """2x2 격자판 이미지에서 지정된 패널 영역을 자동으로 Crop하여 반환"""
    try:
        from PIL import Image
        import io
        from fastapi.responses import StreamingResponse
        
        # Read image
        img_bytes = await file.read()
        image = Image.open(io.BytesIO(img_bytes))
        width, height = image.size
        
        # Calculate grid middle bounds
        mid_x = width // 2
        mid_y = height // 2
        
        # Define crop boxes based on panel index (1-indexed)
        if panel == 1: # Top-Left
            box = (0, 0, mid_x, mid_y)
        elif panel == 2: # Top-Right
            box = (mid_x, 0, width, mid_y)
        elif panel == 3: # Bottom-Left
            box = (0, mid_y, mid_x, height)
        elif panel == 4: # Bottom-Right
            box = (mid_x, mid_y, width, height)
        else:
            raise HTTPException(400, "잘못된 패널 번호입니다. (1-4만 허용)")
            
        # Crop and save to byte stream
        cropped_img = image.crop(box)
        output_stream = io.BytesIO()
        cropped_img.save(output_stream, format="PNG")
        output_stream.seek(0)
        
        return StreamingResponse(output_stream, media_type="image/png")
    except Exception as e:
        raise HTTPException(500, f"이미지 자르기 실패: {str(e)}")
