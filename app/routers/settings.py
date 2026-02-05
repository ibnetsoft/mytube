
from fastapi import APIRouter, HTTPException, UploadFile, File, Form
from pydantic import BaseModel
from typing import Optional, Dict, Any
import database as db
import os
import shutil
import uuid
import time
from config import config

router = APIRouter(prefix="/api/settings", tags=["Settings"])

class GlobalSettings(BaseModel):
    app_mode: Optional[str] = None
    gemini_tts: Optional[Dict[str, Any]] = None
    script_styles: Optional[Dict[str, Any]] = None

@router.get("")
async def get_global_settings_api():
    """글로벌 설정 조회 (Project 1 + Global Table)"""
    # 1. Load Global Table Settings
    global_conf = {
        "app_mode": db.get_global_setting("app_mode", None), # Use None to allow fallback
        "gemini_tts": db.get_global_setting("gemini_tts", {}),
        "script_styles": db.get_global_setting("script_styles", {}),
        "template_image_url": db.get_global_setting("template_image_url")
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
    
    return merged

@router.post("")
async def save_global_settings_api(settings: GlobalSettings):
    """글로벌 설정 저장"""
    if settings.app_mode:
        db.save_global_setting("app_mode", settings.app_mode)
    if settings.gemini_tts:
        db.save_global_setting("gemini_tts", settings.gemini_tts)
    if settings.script_styles:
        db.save_global_setting("script_styles", settings.script_styles)
    return {"status": "ok"}

class StylePreset(BaseModel):
    style_key: str
    prompt_value: str
    image_url: Optional[str] = None

# ===========================================
# API: 이미지 스타일 프리셋 관리
# ===========================================

@router.get("/style-presets")
async def get_style_presets_api():
    """모든 이미지 스타일 프리셋 조회"""
    presets = db.get_style_presets()
    
    # DB에 하나도 없으면 기본값으로 초기화
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
            "3d": "3d render, pixar style, 3d animation, cute, vibrant lighting"
        }
        for key, val in default_styles.items():
            db.save_style_preset(key, val) # image_url=None implicitly
        
        # Reload to get the structured dict
        presets = db.get_style_presets()
        
    return presets

@router.post("/style-presets")
async def save_style_preset_api(preset: StylePreset):
    """이미지 스타일 프리셋 저장"""
    db.save_style_preset(preset.style_key, preset.prompt_value, preset.image_url)
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
            "wimpy": "윔피키드 스타일: 윔피키드(Wimpy Kid) 다이어리 스타일. 흑백의 단순한 선화, 손글씨 폰트, 공책 질감 배경, 유머러스한 낙서 느낌."
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
