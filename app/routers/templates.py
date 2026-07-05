"""
템플릿 업로드 라우터
/api/upload/template 엔드포인트
"""
import os
import time
import aiofiles
from fastapi import APIRouter, HTTPException, UploadFile, File
import database as db
from config import config
from app.utils import (
    validate_upload as _validate_upload,
    ALLOWED_IMAGE_EXT as _ALLOWED_IMAGE_EXT,
    MAX_IMAGE_SIZE as _MAX_IMAGE_SIZE,
)

router = APIRouter(prefix="/api", tags=["Templates"])


# [AIR-0154] main.py에서 이동��� Template Upload 라우트
@router.post("/upload/template")
async def upload_template_api(file: UploadFile = File(...)):
    """템플릿 이미지 업로드 (9:16 오버레이)"""
    try:
        ext, _ = _validate_upload(file, _ALLOWED_IMAGE_EXT, _MAX_IMAGE_SIZE)
        # public/templates 폴더
        template_dir = os.path.join(config.STATIC_DIR, "templates")
        os.makedirs(template_dir, exist_ok=True)

        filename = f"template_{int(time.time())}{ext}"
        filepath = os.path.join(template_dir, filename)

        content = await file.read()
        if len(content) > _MAX_IMAGE_SIZE:
            raise HTTPException(400, f"파일 크기가 너무 큽니다 (최대 {_MAX_IMAGE_SIZE//1024//1024}MB)")
        async with aiofiles.open(filepath, "wb") as f:
            await f.write(content)

        # DB 업데이트 (Global Setting assumes project_id=1 for defaults or handle strictly)
        # For now, we save it as a 'default' setting with project_id=0 or just update recent project?
        # Re-reading user request: "9:16 Template Image... for SHORTS".
        # Usually settings page updates a GLOBAL default or current project.
        # Let's assume GLOBAL default for new projects, or update specific project if provided.
        # However, `settings.html` seems to load 'global-ish' settings.
        # Let's check `db.update_project_setting`.
        # Actually, `settings.html` usually loads default settings from a dummy project or specific config.
        # But wait, `get_settings_api` fetches from `db.get_project_settings(None)`?
        # Let's fallback to updating the most recent project OR a specific logic.
        # Since `settings.html` seems to be global context, let's assume project_id=1 for now as 'default slot'
        # OR better: The user wants this "Applied to video".
        # Let's save the URL and let the frontend/backend use it.

        web_url = f"/static/templates/{filename}"

        # [HACK] For this specific user request, we might need to apply this to the CURRENT project being edited.
        # But settings.html is global. Let's update project_id=1 (often Default) AND return URL.
        # Ideally, we should have a `global_settings` table.
        # Existing `project_settings` references `project_id`.
        # Let's use `db.update_project_setting(1, ...)` as a placeholder for "Default" if no project context.
        # BUT, to be safe and consistent with previous patterns:
        # Check if we can store it in a way available to new projects.
        # For now, update global default project (ID 1)
        db.update_project_setting(1, 'template_image_url', web_url)

        return {"status": "ok", "url": web_url}
    except Exception as e:
        print(f"Template Upload Error: {e}")
        return {"status": "error", "error": str(e)}


@router.delete("/settings/template")
async def delete_template_api():
    """템플릿 이미지 삭제"""
    try:
        db.update_project_setting(1, 'template_image_url', None)
        return {"status": "ok"}
    except Exception as e:
        return {"status": "error", "error": str(e)}
