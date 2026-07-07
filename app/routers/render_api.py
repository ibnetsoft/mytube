from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from typing import Dict, Any, Optional
from app.services.render_orchestrator import render_orchestrator_service

router = APIRouter()

class CreateRenderJobsRequest(BaseModel):
    production_plan: Dict[str, Any] = Field(..., description="The structured production plan")

@router.post("/jobs")
async def create_jobs(request: CreateRenderJobsRequest):
    if not request.production_plan or "production_items" not in request.production_plan:
        raise HTTPException(status_code=400, detail="Invalid production_plan: missing 'production_items'")
    
    result = render_orchestrator_service.create_render_jobs(request.production_plan)
    
    if result.get("error"):
        raise HTTPException(status_code=500, detail=result.get("error_message", "Failed to insert render jobs"))
        
    return result

@router.get("/jobs")
async def get_jobs(
    status: Optional[str] = Query(None, description="Filter by status"),
    generator: Optional[str] = Query(None, description="Filter by generator"),
    asset_type: Optional[str] = Query(None, description="Filter by asset_type")
):
    jobs = render_orchestrator_service.get_render_jobs(status, generator, asset_type)
    return jobs
