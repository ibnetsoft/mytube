from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import Dict, Any, List
from app.services.prompt_director import prompt_director_service

router = APIRouter()

class PlanShotsRequest(BaseModel):
    scenes: List[Dict[str, Any]] = Field(..., description="The planned scenes from Scene Planner")
    mode: Optional[str] = Field("basic", description="Video prompt mode: 'basic' (first 12 scenes only) or 'all'/'full' (all scenes). Default is 'basic'.")

@router.post("/plan-shots")
async def plan_shots(request: PlanShotsRequest):
    if not request.scenes:
        raise HTTPException(status_code=400, detail="Invalid request: missing 'scenes'")
    
    result = await prompt_director_service.enhance_scenes(request.scenes, mode=request.mode or "basic")
    
    # If the service caught an error and returned the fallback with error=True
    if result.get("director_notes", {}).get("error"):
        raise HTTPException(status_code=500, detail=result["director_notes"].get("error_message", "Failed to enhance scenes"))
        
    return result
