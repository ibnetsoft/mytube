from fastapi import APIRouter, HTTPException, BackgroundTasks, Body
from typing import Optional, Dict, Any
import database as db
from services import autopilot_service

router = APIRouter(prefix="/api/queue", tags=["Queue"])

@router.get("/status")
async def get_queue_status():
    """현재 대기열 및 처리 상태 조회"""
    try:
        status = autopilot_service.get_queue_status()
        return {"status": "success", "queue": status}
    except Exception as e:
        raise HTTPException(500, str(e))

@router.post("/add/{project_id}")
async def add_to_queue(project_id: int):
    """프로젝트를 대기열에 추가"""
    try:
        autopilot_service.add_to_queue(project_id)
        return {"status": "success", "message": "Project added to queue"}
    except Exception as e:
        raise HTTPException(500, str(e))

@router.post("/start")
async def start_processing(background_tasks: BackgroundTasks):
    """대기열 처리 시작"""
    try:
        background_tasks.add_task(autopilot_service.run_batch_workflow)
        return {"status": "success", "message": "Batch processing started"}
    except Exception as e:
        raise HTTPException(500, str(e))

@router.post("/clear")
async def clear_queue():
    """대기열 비우기"""
    try:
        autopilot_service.clear_queue()
        return {"status": "success", "message": "Queue cleared"}
    except Exception as e:
        raise HTTPException(500, str(e))
