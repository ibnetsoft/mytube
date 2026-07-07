from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from app.services.script_analyzer import script_analyzer_service
import traceback

router = APIRouter()

class AnalyzeScriptRequest(BaseModel):
    script: str

@router.post("/analyze")
async def analyze_script_endpoint(req: AnalyzeScriptRequest):
    if not req.script or not req.script.strip():
        raise HTTPException(status_code=400, detail="Script content is required")
        
    try:
        result = await script_analyzer_service.analyze_script(req.script)
        return result
    except Exception as e:
        print(f"[ScriptAPI] Error analyzing script: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=str(e))
