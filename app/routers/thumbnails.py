from fastapi import APIRouter, HTTPException, Depends, Body
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
import database as db
from services.gemini_service import gemini_service
import json
import os

router = APIRouter(prefix="/api", tags=["Thumbnails"])

class ThumbnailTextRequest(BaseModel):
    project_id: int
    thumbnail_style: str
    target_language: str = "ko"

class ThumbnailsSave(BaseModel):
    ideas: List[dict]
    texts: List[str]
    full_settings: Optional[dict] = None

@router.post("/thumbnail/generate-text")
async def generate_thumbnail_text(req: ThumbnailTextRequest):
    """썸네일 후킹 문구 생성"""
    try:
        # 1. Get Project Data (Topic, Script)
        project = db.get_project(req.project_id)
        if not project:
            raise HTTPException(404, "Project not found")
        
        script_data = db.get_script(req.project_id)
        script = script_data.get('full_script', '') if script_data else ''
        topic = project.get('topic') or project.get('name')

        # 2. Call Gemini Service
        # We need a specialized prompt for hooking text based on style
        result = await gemini_service.generate_thumbnail_texts(
             topic=topic,
             script=script,
             style=req.thumbnail_style,
             language=req.target_language
        )
        
        return {"status": "ok", "texts": result.get('texts', []), "reasoning": result.get('reasoning', '')}

    except Exception as e:
        print(f"Hook text gem_error: {e}")
        return {"status": "error", "error": str(e)}

@router.post("/projects/{project_id}/thumbnails")
async def save_thumbnails(project_id: int, req: ThumbnailsSave):
    """썸네일 설정 저장"""
    try:
        # Save ideas/texts (Legacy/Backwards compatible)
        db.save_thumbnails(project_id, req.ideas, req.texts, req.full_settings)
        
        # Save full settings (New)
        if req.full_settings:
            import json
            db.update_project_setting(project_id, 'thumbnail_full_state', json.dumps(req.full_settings, ensure_ascii=False))
            
            # 스타일 업데이트
            style = req.full_settings.get('style')
            if style:
                db.update_project_setting(project_id, 'thumbnail_style', style)

            # 텍스트 레이어에서 대표 폰트/색상 정보 추출 및 저장
            text_layers = req.full_settings.get('textLayers', [])
            if text_layers and len(text_layers) > 0:
                main_layer = text_layers[0] # 첫 번째 레이어를 기준으로 저장
                
                # 개별 설정 동기화
                db.update_project_setting(project_id, 'thumbnail_font', main_layer.get('font_family', 'Recipekorea'))
                db.update_project_setting(project_id, 'thumbnail_font_size', main_layer.get('font_size', 75))
                db.update_project_setting(project_id, 'thumbnail_color', main_layer.get('color', '#FFFFFF'))
                
                # 메인 텍스트도 업데이트 (있는 경우)
                if main_layer.get('text'):
                    db.update_project_setting(project_id, 'thumbnail_text', main_layer['text'])

        return {"status": "ok"}
    except Exception as e:
        print(f"Save thumbnails error: {e}")
        return {"status": "error", "error": str(e)}

@router.get("/projects/{project_id}/thumbnails")
async def get_thumbnails(project_id: int):
    """썸네일 설정 조회"""
    try:
        # 1. Load from legacy thumbnails table (includes older full_settings)
        data = db.get_thumbnails(project_id) or {}
        full_settings = data.get('full_settings') or {}
        
        # 2. Try newer project_settings table as fallback/expansion
        settings = db.get_project_settings(project_id)
        full_state_json = settings.get('thumbnail_full_state')
        if full_state_json:
            try:
                server_settings = json.loads(full_state_json)
                if server_settings and not full_settings:
                    full_settings = server_settings
                elif server_settings:
                    # Merge or use more recent? Let's prefer server_settings if it exists
                    full_settings = server_settings
            except Exception:
                pass
        
        return {
            "status": "ok",
            "ideas": data.get('ideas', []),
            "texts": data.get('texts', []),
            "full_settings": full_settings
        }
    except Exception as e:
        print(f"Get thumbnails error: {e}")
        return {"status": "error", "error": str(e)}


class DefaultStyleSave(BaseModel):
    textLayers: List[dict]
    shapeLayers: List[dict]

@router.post("/thumbnail/default-style")
async def save_default_style(req: DefaultStyleSave):
    """전역 기본 썸네일 스타일 저장 (텍스트 내용 제외, 스타일만)"""
    try:
        style_data = {
            "textLayers": [
                {k: v for k, v in layer.items() if k != 'text'}
                for layer in req.textLayers
            ],
            "shapeLayers": req.shapeLayers
        }
        db.save_global_setting("thumbnail_default_style", json.dumps(style_data, ensure_ascii=False))
        return {"status": "ok"}
    except Exception as e:
        return {"status": "error", "error": str(e)}

@router.get("/thumbnail/default-style")
async def get_default_style():
    """전역 기본 썸네일 스타일 조회"""
    try:
        raw = db.get_global_setting("thumbnail_default_style", None)
        if not raw:
            return {"status": "ok", "style": None}
        return {"status": "ok", "style": json.loads(raw)}
    except Exception as e:
        return {"status": "error", "error": str(e)}

# ===========================================
# Shorts Template Presets
# ===========================================

class ShortsTemplatePresetSave(BaseModel):
    name: str
    settings: dict
    image_data: Optional[str] = None # Base64 PNG
    category: Optional[str] = "shorts"

@router.get("/shorts-template/presets")
async def get_shorts_template_presets(category: str = "shorts"):
    """숏폼 템플릿 프리셋 목록 조회"""
    try:
        presets = db.get_shorts_template_presets(category)
        # Parse settings_json
        for p in presets:
            if p.get('settings_json'):
                p['settings'] = json.loads(p['settings_json'])
        return {"status": "ok", "presets": presets}
    except Exception as e:
        return {"status": "error", "error": str(e)}

@router.get("/shorts-template/preset/{name}")
async def get_shorts_template_preset(name: str, category: str = "shorts"):
    """특정 숏폼 템플릿 프리셋 상세 조회"""
    try:
        preset = db.get_shorts_template_preset(name, category)
        if not preset:
            return {"status": "error", "error": "프리셋을 찾을 수 없습니다."}
        
        # Parse settings_json
        if preset.get('settings_json'):
            preset['settings'] = json.loads(preset['settings_json'])
            
        return {"status": "ok", "preset": preset}
    except Exception as e:
        return {"status": "error", "error": str(e)}

@router.post("/shorts-template/presets")
async def save_shorts_template_preset(req: ShortsTemplatePresetSave):
    """숏폼 템플릿 프리셋 저장"""
    try:
        if not req.name:
            return {"status": "error", "error": "프리셋 이름을 입력하세요."}
        
        image_path = None
        if req.image_data:
            import base64
            from config import config
            import uuid
            
            # Save base64 image to assets/templates
            header, encoded = req.image_data.split(",", 1)
            data = base64.b64decode(encoded)
            
            # [Robustness] Use config.ASSETS_DIR if available, else calculate fallback
            base_assets = getattr(config, 'ASSETS_DIR', os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "assets"))
            tpl_dir = os.path.join(base_assets, "templates")
            os.makedirs(tpl_dir, exist_ok=True)
            
            filename = f"template_{uuid.uuid4().hex}.png"
            image_path = os.path.join(tpl_dir, filename)
            
            with open(image_path, "wb") as f:
                f.write(data)
        
        db.save_shorts_template_preset(req.name, json.dumps(req.settings, ensure_ascii=False), image_path, req.category)
        return {"status": "ok"}
    except Exception as e:
        return {"status": "error", "error": str(e)}

@router.delete("/shorts-template/presets/{name}")
async def delete_shorts_template_preset(name: str, category: str = "shorts"):
    """숏폼 템플릿 프리셋 삭제"""
    try:
        db.delete_shorts_template_preset(name, category)
        return {"status": "ok"}
    except Exception as e:
        return {"status": "error", "error": str(e)}
