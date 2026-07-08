from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from typing import Dict, Any, Optional
import os

from app.services.prompt_package_builder import prompt_package_builder_service

router = APIRouter()

class BuildPackageRequest(BaseModel):
    production_plan: Dict[str, Any] = Field(..., description="The structured production plan")
    project_id: str = Field(..., description="The unique project ID")

@router.post("/build")
async def build_package(request: BuildPackageRequest):
    if not request.production_plan or "production_items" not in request.production_plan:
        raise HTTPException(status_code=400, detail="Invalid production_plan: missing 'production_items'")
    
    try:
        result = prompt_package_builder_service.build_package(request.production_plan, request.project_id)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/download/{package_id}")
async def download_package(package_id: str):
    # Find the matching package in the temp directory
    packages_dir = prompt_package_builder_service.packages_dir
    
    # Very basic search, assuming Project_Prompt_Package_*{package_id}.zip
    target_file = None
    for f in os.listdir(packages_dir):
        if f.endswith(f"{package_id}.zip"):
            target_file = os.path.join(packages_dir, f)
            break
            
    if not target_file or not os.path.exists(target_file):
        raise HTTPException(status_code=404, detail="Package not found")
        
    return FileResponse(
        target_file, 
        media_type='application/zip', 
        filename=f"prompt_package_{package_id}.zip"
    )
