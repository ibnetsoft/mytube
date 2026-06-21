from fastapi import APIRouter
from services.updater_service import updater_service
from pydantic import BaseModel

router = APIRouter(prefix="/api/update", tags=["Update"])

class DownloadRequest(BaseModel):
    url: str

@router.get("/check")
async def check_update():
    return updater_service.check_for_update()

@router.post("/download")
async def start_download(req: DownloadRequest):
    updater_service.start_download(req.url)
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
    success = updater_service.apply_update_and_restart()
    if not success:
        return {"success": False, "error": "Update file not found"}
    return {"success": True}
