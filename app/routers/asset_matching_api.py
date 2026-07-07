from fastapi import APIRouter, HTTPException, UploadFile, File, Form
from pydantic import BaseModel, Field
from typing import Dict, Any, List, Optional
import os

from app.services.asset_upload_service import asset_upload_service
from app.services.asset_matching_service import asset_matching_service
from services.web_admin_client import web_admin_client

router = APIRouter()

class OverrideMatchRequest(BaseModel):
    match_id: str
    scene_id: str
    shot_id: str

@router.post("/upload")
async def upload_asset(
    project_id: str = Form(...),
    user_id: str = Form(...),
    file: UploadFile = File(...),
    # Optional mocked shots payload for preview testing
    mock_shots_json: Optional[str] = Form(None)
):
    # Determine type
    file_type = "video" if file.content_type and "video" in file.content_type else "image"
    mime_type = file.content_type or "application/octet-stream"
    
    # 1. Process Upload & Analysis
    upload_res = asset_upload_service.process_upload(
        project_id=project_id,
        user_id=user_id,
        file_name=file.filename,
        file_type=file_type,
        mime_type=mime_type,
        file_size=file.size or 0
    )
    
    if not upload_res.get("success"):
        raise HTTPException(status_code=500, detail="Failed to upload and analyze asset")
        
    asset = upload_res["asset"]
    
    # 2. Auto-Match (if shots are provided. Real app fetches from DB via project_id)
    shots = []
    if mock_shots_json:
        import json
        try:
            shots = json.loads(mock_shots_json)
        except Exception:
            pass
            
    match_result = None
    if shots:
        match_res = asset_matching_service.auto_match_asset(asset, shots)
        if match_res.get("success"):
            match_result = match_res["match"]
            
    return {
        "asset": asset,
        "match": match_result
    }

@router.get("/project/{project_id}")
async def get_project_assets(project_id: str):
    # Fetch assets
    assets_resp = web_admin_client.supabase_get("uploaded_assets", params={"project_id": f"eq.{project_id}"})
    assets = assets_resp.json() if assets_resp and assets_resp.status_code == 200 else []
    
    # Fetch matches
    matches_resp = web_admin_client.supabase_get("asset_scene_matches", params={"project_id": f"eq.{project_id}"})
    matches = matches_resp.json() if matches_resp and matches_resp.status_code == 200 else []
    
    return {
        "assets": assets,
        "matches": matches
    }

class MatchStatusRequest(BaseModel):
    match_id: str
    status: str

@router.patch("/matches/override")
async def override_match(req: OverrideMatchRequest):
    success = asset_matching_service.override_match(req.match_id, req.scene_id, req.shot_id)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to override match")
    return {"success": True}

@router.patch("/matches/status")
async def update_match_status(req: MatchStatusRequest):
    success = asset_matching_service.update_match_status(req.match_id, req.status)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to update match status")
    return {"success": True}
