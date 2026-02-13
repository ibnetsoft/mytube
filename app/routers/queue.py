from fastapi import APIRouter, HTTPException, BackgroundTasks, Body
from typing import Optional, Dict, Any
from pydantic import BaseModel
import database as db
from services import autopilot_service

router = APIRouter(tags=["Queue"])

class AutopilotQueueRequest(BaseModel):
    topic: str
    script_style: str
    duration_seconds: int
    auto_plan: bool = True
    all_video: bool = False
    motion_method: str = "standard"
    video_scene_count: int = 0
    visual_style: str = "realistic"
    thumbnail_style: str = "face"

@router.get("/api/queue/status")
async def get_queue_status():
    """현재 대기열 및 처리 상태 조회"""
    try:
        status = autopilot_service.get_queue_status()
        return {"status": "success", "queue": status}
    except Exception as e:
        raise HTTPException(500, str(e))

@router.post("/api/projects/{project_id}/queue")
async def add_project_to_queue(project_id: int, req: AutopilotQueueRequest):
    """프로젝트를 대기열에 추가 (대본 존재 여부 확인)"""
    try:
        # [NEW Check] Ensure script exists and is long enough
        settings = db.get_project_settings(project_id)
        if not settings or not settings.get('script') or len(settings.get('script').strip()) < 50:
             raise HTTPException(400, "대본이 생성되지 않은 프로젝트는 대기열에 추가할 수 없습니다.")

        # Update project status and settings
        db.update_project(project_id, status="queued", topic=req.topic)
        
        save_data = {
            "script_style": req.script_style,
            "duration_seconds": req.duration_seconds,
            "auto_plan": req.auto_plan,
            "auto_thumbnail": True,
            "visual_style": req.visual_style, 
            "thumbnail_style": req.thumbnail_style,
            "all_video": 1 if req.all_video else 0,
            "motion_method": req.motion_method,
            "video_scene_count": req.video_scene_count
        }
        
        for k, v in save_data.items():
            db.update_project_setting(project_id, k, v)
             
        return {"status": "ok", "message": "Project added to queue"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, str(e))

@router.post("/api/queue/start")
async def start_processing(background_tasks: BackgroundTasks):
    """대기열 처리 시작"""
    try:
        background_tasks.add_task(autopilot_service.run_batch_workflow)
        return {"status": "success", "message": "Batch processing started"}
    except Exception as e:
        raise HTTPException(500, str(e))

@router.post("/api/queue/clear")
async def clear_queue():
    """대기열 비우기"""
    try:
        autopilot_service.clear_queue()
        return {"status": "success", "message": "Queue cleared"}
    except Exception as e:
        raise HTTPException(500, str(e))
