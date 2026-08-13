from fastapi import APIRouter, HTTPException
from services.updater_service import updater_service
from pydantic import BaseModel

router = APIRouter(prefix="/api/update", tags=["Update"])

class DownloadRequest(BaseModel):
    url: str
    sha256: str | None = None

@router.get("/check")
async def check_update():
    return updater_service.check_for_update()

@router.post("/download")
async def start_download(req: DownloadRequest):
    if not updater_service.start_download(req.url, req.sha256):
        raise HTTPException(
            status_code=409,
            detail=updater_service.download_error or "Update download is already in progress",
        )
    return {"success": True, "message": "Download started"}

@router.get("/status")
async def check_status():
    return {
        "is_downloading": updater_service.is_downloading,
        "progress": updater_service.download_progress,
        "error": updater_service.download_error
    }

@router.post("/apply")
async def apply_update():
    # Will not return if successful because the app restarts
    success, error = updater_service.apply_update_and_restart()
    if not success:
        return {"success": False, "error": error}
    return {"success": True}
