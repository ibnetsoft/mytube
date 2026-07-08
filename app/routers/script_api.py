from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from app.services.scene_planner import scene_planner_service
import traceback

router = APIRouter()

class PlanScenesRequest(BaseModel):
    topic: str
    target_duration: int = 60

@router.post("/plan")
async def plan_scenes_endpoint(req: PlanScenesRequest):
    if not req.topic or not req.topic.strip():
        raise HTTPException(status_code=400, detail="Topic is required")
        
    try:
        result = await scene_planner_service.plan_scenes(req.topic, req.target_duration)
        return result
    except Exception as e:
        print(f"[ScriptAPI] Error planning scenes: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=str(e))
