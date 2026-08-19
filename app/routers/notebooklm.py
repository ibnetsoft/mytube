"""
FastAPI Router for NotebookLM Grounded Script & Dialogue Generation
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from services.notebooklm_service import generate_notebooklm_project

router = APIRouter(prefix="/api/notebooklm", tags=["NotebookLM"])

class NotebookLMGenerateRequest(BaseModel):
    source_text: str = Field(..., description="Reference document or notes to ground script on")
    mode: str = Field("dialogue_podcast", description="'dialogue_podcast' (2 hosts) or 'narrator' (1 host)")
    category: str = Field("옛날이야기", description="Target category")
    duration_minutes: int = Field(15, description="Target duration in minutes")
    custom_title: Optional[str] = Field(None, description="Optional custom title")

@router.post("/generate")
async def generate_script(req: NotebookLMGenerateRequest):
    try:
        data = await generate_notebooklm_project(
            source_text=req.source_text,
            mode=req.mode,
            category=req.category,
            duration_minutes=req.duration_minutes,
            custom_title=req.custom_title
        )
        return {"success": True, "data": data}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))