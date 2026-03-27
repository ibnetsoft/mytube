from fastapi import APIRouter, HTTPException, BackgroundTasks, Body
from typing import Optional, Dict, Any
from pydantic import BaseModel
import database as db
from services.autopilot_service import autopilot_service

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

@router.get("/api/autopilot/queue")
async def get_autopilot_queue():
    """autopilot 페이지 대기열 조회 (JS 호환)"""
    try:
        projects = db.get_all_projects()
        skip = {"done", "error", "draft", "created", "planning"}
        active = [p for p in projects if p.get("status") and p["status"] not in skip]
        # 최근 프로젝트만 (ID 기준 상위 20개)
        active.sort(key=lambda x: x.get("id", 0), reverse=True)
        active = active[:20]

        # 채널 목록 미리 로드 (이름 매핑용)
        channels = db.get_all_channels()
        channel_map = {c["id"]: c["name"] for c in channels}

        # 각 프로젝트에 채널 정보 포함
        for p in active:
            settings = db.get_project_settings(p["id"]) or {}
            ch_id = settings.get("youtube_channel_id")
            ch_id_int = int(ch_id) if ch_id else None
            p["youtube_channel_id"] = ch_id_int
            p["channel_name"] = channel_map.get(ch_id_int) if ch_id_int else None

        return {"projects": active, "count": len(active)}
    except Exception as e:
        raise HTTPException(500, str(e))


class UpdateChannelRequest(BaseModel):
    youtube_channel_id: Optional[int] = None


@router.patch("/api/queue/{project_id}/channel")
async def update_queue_item_channel(project_id: int, req: UpdateChannelRequest):
    """대기열 항목의 업로드 채널 변경"""
    try:
        project = db.get_project(project_id)
        if not project:
            raise HTTPException(404, "프로젝트를 찾을 수 없습니다.")
        if project.get("status") != "queued":
            raise HTTPException(400, "대기열 상태의 프로젝트만 변경 가능합니다.")

        db.update_project_setting(project_id, "youtube_channel_id", req.youtube_channel_id)
        return {"status": "ok", "message": "채널이 변경되었습니다."}
    except HTTPException:
        raise
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
    """대기열 처리 시작 (배치 워커가 이미 실행 중이면 그대로 성공 반환)"""
    try:
        if autopilot_service.is_batch_running:
            return {"status": "success", "message": "Batch worker already running"}
        background_tasks.add_task(autopilot_service.run_batch_workflow)
        return {"status": "success", "message": "Batch processing started"}
    except Exception as e:
        raise HTTPException(500, str(e))

@router.get("/api/queue/logs")
async def get_queue_logs():
    """최신 시스템 로그 (debug.log) 조회"""
    from config import config
    import os
    log_path = config.DEBUG_LOG_PATH
    if not os.path.exists(log_path):
        return {"logs": ["No logs yet."]}
    
    try:
        with open(log_path, "r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
            return {"logs": lines[-50:]}
    except Exception as e:
        return {"logs": [f"Error reading logs: {str(e)}"]}

@router.post("/api/queue/clear")
async def clear_queue():

    """대기열 비우기"""
    try:
        autopilot_service.clear_queue()
        return {"status": "success", "message": "Queue cleared"}
    except Exception as e:
        raise HTTPException(500, str(e))
