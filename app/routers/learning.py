"""Learning/event log API routes."""

from typing import Any, Dict, Optional

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field

import database as db
from services import learning_service

router = APIRouter(prefix="/api/projects", tags=["learning"])
admin_router = APIRouter(prefix="/api/admin/learning", tags=["learning"])


class LearningEventCreate(BaseModel):
    event_type: str = Field(..., min_length=1)
    stage: str = ""
    source: str = "user"
    payload: Dict[str, Any] = Field(default_factory=dict)


class LearningSnapshotCreate(BaseModel):
    snapshot_type: str = "manual_review"
    extra: Optional[Dict[str, Any]] = None


@admin_router.post("/sync")
async def sync_admin_learning_data(limit: int = Query(100, ge=1, le=500)):
    from services.learning_sync_service import sync_learning_data
    return {"status": "ok", "sync": sync_learning_data(limit)}


@admin_router.get("/stats")
async def get_admin_learning_stats(limit: int = Query(100, ge=1, le=500)):
    try:
        from services.learning_sync_service import sync_learning_data
        sync_learning_data(limit)
    except Exception as exc:
        print(f"[Learning] Admin stats remote sync skipped: {exc}")
    return {"status": "ok", "stats": db.get_learning_admin_stats(limit)}


@router.post("/{project_id}/learning/events")
async def create_learning_event(project_id: int, req: LearningEventCreate):
    event_id = learning_service.log_event(
        project_id=project_id,
        event_type=req.event_type,
        stage=req.stage,
        payload=req.payload,
        source=req.source,
    )
    return {"status": "ok", "event_id": event_id}


@router.get("/{project_id}/learning/events")
async def list_learning_events(project_id: int, limit: int = Query(200, ge=1, le=1000)):
    return {"status": "ok", "events": db.get_learning_events(project_id, limit)}


@router.post("/{project_id}/learning/snapshot")
async def create_learning_snapshot(project_id: int, req: LearningSnapshotCreate):
    snapshot_id = learning_service.snapshot_project(project_id, req.snapshot_type, req.extra)
    return {"status": "ok", "snapshot_id": snapshot_id}


@router.get("/{project_id}/learning/summary")
async def get_learning_summary(project_id: int):
    return {"status": "ok", **learning_service.get_project_summary(project_id)}
