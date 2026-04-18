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

router = APIRouter(prefix="/api/settings", tags=["Settings"])

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
        "user_email": db.get_global_setting("user_email", "")
    }
    
    # 2. Load Default Settings (stored in Project 1 by convention)
    default_project_settings = db.get_project_settings(1) or {}
    
    # 3. Merge (Project 1 is base, Global Table overrides specific keys)
    # But for app_mode, we want Global Table value if exists, else Project 1
    merged = default_project_settings.copy()
    
    # Update only non-None values from global_conf or specific logic
    if global_conf["app_mode"]:
        merged["app_mode"] = global_conf["app_mode"]
    
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
    
    # [NEW] Add Current API Keys Status
    api_status = config.get_api_keys_status()
    merged["api_status"] = api_status
    
    return merged

@router.post("")
async def save_global_settings_api(settings: GlobalSettings):
    """글로벌 설정 저장"""
    # 이전 모드 저장 (모드 변경 감지용)
    previous_mode = db.get_global_setting("app_mode", "longform")
    
    if settings.app_mode:
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
    
    # [NEW] Sync to SaaS server
    from services.auth_service import auth_service
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

# ===========================================
# API: 이미지 스타일 프리셋 관리
# ===========================================

@router.get("/style-presets")
async def get_style_presets_api(mode: Optional[str] = None):
    """이미지 스타일 프리셋 조회. mode=image|blog|all 필터 가능"""
    presets = db.get_style_presets()

    # DB가 완전 비어있을 때만 기본 스타일 초기화 (삭제한 스타일은 재추가 안 함)
    if not presets:
        default_styles = {
            "realistic": "photorealistic, 8k uhd, high quality, detailed",
            "anime": "anime style, vibrant colors, studio ghibli inspired",
            "cinematic": "cinematic lighting, dramatic, movie still, bokeh",
            "cartoon": "cartoon style, cel shading, vibrant, playful",
            "oil_painting": "oil painting, brush strokes, artistic, classic",
            "watercolor": "watercolor painting, soft colors, artistic",
            "sketch": "pencil sketch, hand drawn, artistic, detailed",
            "pixel_art": "pixel art, 16-bit style, retro gaming",
            "3d": "3d render, pixar style, 3d animation, cute, vibrant lighting",
            "k_webtoon": "Modern K-webtoon manhwa style, high-quality digital illustration, sharp line art, vibrant colors, expressive character, modern manhwa aesthetic, professional digital art, no text, no speech bubbles",
            "k_manhwa": "Korean manhwa webtoon illustration style, bold black outlines, cel-shading, vibrant flat colors, anime-inspired character design, dynamic composition, professional digital art, modern Korean comic aesthetic. ABSOLUTELY NO TEXT.",
        }
        for key, val in default_styles.items():
            db.save_style_preset(key, val)
        presets = db.get_style_presets()

    # 새로 추가된 시스템 스타일만 없을 때 개별 삽입 (기존 스타일과 독립)
    _new_system_styles = {
        "animal_cooking_shorts": {
            "prompt": (
                "Warm cozy photorealistic scene, anthropomorphic animals wearing aprons and chef hats, "
                "natural soft warm lighting, high quality food photography style, rich textures of ingredients "
                "and cooking tools, adorable expressive animal faces, 9:16 vertical shorts format"
            ),
            "gemini_instruction": (
                "[쇼츠 3x2 시퀀스 생성기 - 필수 준수]\n"
                "반드시 정확히 6개의 씬을 아래 스토리보드 순서대로 생성하세요. "
                "캐릭터는 부모 동물 1마리 + 아기 동물 2마리 총 3마리입니다. "
                "모든 씬은 동일한 캐릭터·배경·조명·스타일로 일관성을 유지하세요.\n\n"
                "씬1 (재료 준비 1): 부모 동물이 주요 재료를 씻거나 다듬고 있습니다. "
                "아기 동물 한 마리가 옆에서 호기심 어린 눈으로 바라보거나 작은 도구를 들고 돕는 시늉을 합니다.\n"
                "씬2 (재료 준비 2): 다른 재료를 손질하거나 섞는 과정입니다. "
                "아기 동물 두 마리가 밀가루를 묻히거나 재료로 장난치는 귀엽고 서툰 모습. 부모 동물은 흐뭇하게 바라봅니다.\n"
                "씬3 (조리 시작): 냄비나 팬에 재료를 넣고 조리를 시작합니다. "
                "불 위에서 재료가 볶아지거나 끓으며 김이 모락모락 납니다. 세 마리가 함께 불 앞을 지켜봅니다.\n"
                "씬4 (조리 중): 요리가 한창 진행 중입니다. 오븐 속에서 굽거나 냄비에서 보글보글 끓고 있습니다. "
                "음식 색감이 먹음직스럽게 변해가고 아기 동물들이 기대에 찬 표정으로 기다립니다.\n"
                "씬5 (조리 완료): 완성된 요리를 예쁜 그릇에 플레이팅하는 장면입니다. "
                "부모 동물이 마지막 장식을 더하고, 아기 동물들은 숟가락을 들고 먹을 준비를 완료하며 기뻐합니다.\n"
                "씬6 (함께 식사): 세 마리가 식탁에 둘러앉아 완성된 요리를 행복하게 먹는 장면입니다. "
                "모두 입가에 음식을 묻히며 만족스러운 표정, 따뜻하고 화목한 분위기의 절정.\n\n"
                "스타일 요구사항:\n"
                "- 의인화된 동물: 앞치마·요리 모자 착용, 표정에서 즐거움과 행복함이 느껴질 것\n"
                "- 따뜻하고 아늑한 분위기, 자연광 활용한 부드러운 사진 스타일\n"
                "- 동물 털 질감·음식 식재료 질감·요리 도구 디테일을 생생하게 표현\n"
                "- 6개 씬 전체가 하나의 연속된 이야기처럼 자연스럽게 연결될 것"
            )
        },
    }
    needs_reload = False
    for key, data in _new_system_styles.items():
        if key not in presets:
            db.save_style_preset(key, data["prompt"], image_url=None,
                                 gemini_instruction=data.get("gemini_instruction"),
                                 mode=data.get("mode", "image"))
            needs_reload = True
    if needs_reload:
        presets = db.get_style_presets()

    # sports_analysis가 있으면 mode를 'blog'로 설정 (아직 'image'인 경우만)
    if 'sports_analysis' in presets and presets['sports_analysis'].get('mode', 'image') == 'image':
        db.save_style_preset('sports_analysis',
                             presets['sports_analysis']['prompt_value'],
                             mode='blog')
        needs_reload = True
    if needs_reload:
        presets = db.get_style_presets()

    # mode 쿼리 파라미터 필터 적용
    if mode:
        presets = {k: v for k, v in presets.items() if v.get('mode') == mode or v.get('mode') == 'all'}

    return presets

@router.post("/style-presets")
async def save_style_preset_api(preset: StylePreset):
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

@router.delete("/style-presets/{style_key}")
async def delete_style_preset(style_key: str):
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

@router.get("/script-style-presets")
async def get_script_style_presets_api():
    """모든 대본 스타일 프리셋 조회"""
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
    try:
        db.save_webtoon_rule(req.condition_type, req.condition_value, req.action_type, req.description)
        return {"status": "success"}
    except Exception as e:
        raise HTTPException(500, str(e))

@router.delete("/webtoon-rules/{rule_id}")
async def delete_webtoon_rule_api(rule_id: int):
    try:
        db.delete_webtoon_rule(rule_id)
        return {"status": "success"}
    except Exception as e:
        raise HTTPException(500, str(e))
