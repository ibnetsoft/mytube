from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import Dict, Any
from app.services.production_planner import production_planner_service

router = APIRouter()

class PlanProductionRequest(BaseModel):
    shot_plan: Dict[str, Any] = Field(..., description="The structured shot plan from Director AI")

@router.post("/plan")
async def plan_production(request: PlanProductionRequest):
    if not request.shot_plan or "shots" not in request.shot_plan:
        raise HTTPException(status_code=400, detail="Invalid shot_plan: missing 'shots'")
    
    result = await production_planner_service.plan_production(request.shot_plan)
    
    if result.get("planner_notes", {}).get("error"):
        raise HTTPException(status_code=500, detail=result["planner_notes"].get("error_message", "Failed to plan production"))
        
    return result
