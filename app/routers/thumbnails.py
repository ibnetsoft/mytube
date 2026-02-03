from fastapi import APIRouter, HTTPException, Depends, Body
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
import database as db
from services.gemini_service import gemini_service
import json

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
        db.save_thumbnails(project_id, req.ideas, req.texts)
        
        # Save full settings (New)
        if req.full_settings:
            # We can store this in a JSON column or a separate table.
            # For now, let's use a specific key in project_settings or a new table.
            # Since user wants "Save Settings" to be robust, let's update project_settings
            # with a specific key 'thumbnail_full_state'
            import json
            db.update_project_setting(project_id, 'thumbnail_full_state', json.dumps(req.full_settings))
            
            # Also update discrete fields for easier access if needed
            if req.full_settings.get('style'):
                db.update_project_setting(project_id, 'thumbnail_style', req.full_settings['style'])

        return {"status": "ok"}
    except Exception as e:
        print(f"Save thumbnails error: {e}")
        return {"status": "error", "error": str(e)}

@router.get("/projects/{project_id}/thumbnails")
async def get_thumbnails(project_id: int):
    """썸네일 설정 조회"""
    try:
        # Load legacy
        data = db.get_thumbnails(project_id) or {}
        
        # Load full settings
        settings = db.get_project_settings(project_id)
        full_state_json = settings.get('thumbnail_full_state')
        full_settings = {}
        if full_state_json:
            try:
                full_settings = json.loads(full_state_json)
            except:
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
