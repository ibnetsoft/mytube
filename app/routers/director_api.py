from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import Dict, Any
from app.services.director_ai import director_ai_service

router = APIRouter()

class PlanShotsRequest(BaseModel):
    script_analysis: Dict[str, Any] = Field(..., description="The scenes and script metadata from Script Analyzer")

@router.post("/plan-shots")
async def plan_shots(request: PlanShotsRequest):
    if not request.script_analysis or "scenes" not in request.script_analysis:
        raise HTTPException(status_code=400, detail="Invalid script_analysis: missing 'scenes'")
    
    result = await director_ai_service.plan_shots(request.script_analysis)
    
    # If the service caught an error and returned the fallback with error=True
    if result.get("director_notes", {}).get("error"):
        raise HTTPException(status_code=500, detail=result["director_notes"].get("error_message", "Failed to plan shots"))
        
    return result
