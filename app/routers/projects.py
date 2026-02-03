
from fastapi import APIRouter, HTTPException, BackgroundTasks, Form, Body
from typing import Dict, Any, Optional
import database as db
import os
import re
import datetime
import json
from config import config
from pydantic import BaseModel
from services.gemini_service import gemini_service

router = APIRouter(prefix="/api/projects", tags=["Projects"])

# Models (Moved from main.py)
class ProjectCreate(BaseModel):
    name: str
    topic: Optional[str] = None
    target_language: Optional[str] = "ko"

class ProjectUpdate(BaseModel):
    name: Optional[str] = None
    topic: Optional[str] = None
    status: Optional[str] = None
    
class AnalysisSave(BaseModel):
    video_data: dict
    analysis_result: dict

class ScriptStructureSave(BaseModel):
    hook: str
    sections: list
    cta: str
    style: str
    duration: int

# Helper used by main.py
def get_project_output_dir(project_id: int):
    """
    프로젝트 ID를 기반으로 '프로젝트명_날짜' 형식의 폴더를 생성하고 경로를 반환합니다.
    """
    project = db.get_project(project_id)
    if not project:
        return config.OUTPUT_DIR, "/output" # Fallback

    # 폴더명 생성 (프로젝트명 + 생성일자 YYYYMMDD)
    safe_name = re.sub(r'[\\/*?:"<>|]', "", project['name']).strip().replace(" ", "_")
    today = datetime.datetime.now().strftime("%Y%m%d")
    folder_name = f"{safe_name}_{today}"
    
    # 전체 경로
    abs_path = os.path.join(config.OUTPUT_DIR, folder_name)
    os.makedirs(abs_path, exist_ok=True)
    
    web_path = f"/output/{folder_name}"
    
    return abs_path, web_path

# ============ 학습 시스템 백그라운드 태스크 ============
async def background_learn_strategy(video_id: str, analysis_result: dict, script_style: str = "story"):
    """백그라운드에서 분석 결과를 기반으로 지식 추출 및 저장"""
    try:
        print(f"[Learning] Starting strategy extraction for video: {video_id}...")
        strategies = await gemini_service.extract_success_strategy(analysis_result)
        if strategies:
            for s in strategies:
                db.save_success_knowledge(
                    category=s.get('category'),
                    pattern=s.get('pattern'),
                    insight=s.get('insight'),
                    source_video_id=video_id,
                    script_style=s.get('script_style', script_style)
                )
            print(f"[Learning] Successfully learned {len(strategies)} strategies from {video_id}")
        else:
            print(f"[Learning] No strategies extracted from {video_id}")
    except Exception as e:
        import traceback
        print(f"[Learning] Failed to learn from {video_id}: {e}")
        traceback.print_exc()

# ===========================================
# API: 프로젝트 기본 CRUD
# ===========================================

@router.get("/")
async def get_projects():
    """모든 프로젝트 목록 (상태 포함)"""
    return {"projects": db.get_projects_with_status()}

@router.post("/")
async def create_project(req: ProjectCreate):
    """새 프로젝트 생성"""
    # Check Global App Mode if not specified (Assuming stored in project settings or other global config)
    # Since we don't have direct access to 'settings_service' easily without circular imports potentially,
    # we can re-implement a simple check or import inside.
    
    try:
        from services.settings_service import settings_service
        global_settings = settings_service.get_settings()
        current_app_mode = global_settings.get("app_mode", "longform")
    except:
        current_app_mode = "longform"
    
    project_id = db.create_project(req.name, req.topic, app_mode=current_app_mode)
    
    # 언어 설정 저장
    if req.target_language:
        db.update_project_setting(project_id, 'target_language', req.target_language)
        
    return {"status": "ok", "project_id": project_id}

@router.get("/{project_id}")
async def get_project(project_id: int):
    """프로젝트 상세 조회"""
    project = db.get_project(project_id)
    if not project:
        raise HTTPException(404, "프로젝트를 찾을 수 없습니다")
    return project

@router.put("/{project_id}")
async def update_project(project_id: int, req: ProjectUpdate):
    """프로젝트 업데이트"""
    updates = {k: v for k, v in req.dict().items() if v is not None}
    if updates:
        db.update_project(project_id, **updates)
    return {"status": "ok"}


@router.delete("/{project_id}")
async def delete_project(project_id: int):
    """프로젝트 삭제"""
    try:
        db.delete_project(project_id)
        return {"status": "ok"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.patch("/{project_id}")
async def update_project_details(project_id: int, data: Dict[str, Any]):
    """프로젝트 정보 (이름, 주제, 제목) 업데이트"""
    try:
        # 1. projects 테이블 정보 업데이트 (name, topic)
        project_updates = {}
        if "name" in data: project_updates["name"] = data["name"]
        if "topic" in data: project_updates["topic"] = data["topic"]
        
        if project_updates:
            db.update_project(project_id, **project_updates)
            
            # [NEW] Sync Topic to Global Settings (Project 1) for Autopilot
            if "topic" in project_updates:
                db.update_project_setting(1, "last_topic", project_updates["topic"])
            
        # 2. project_settings 테이블 정보 업데이트 (title -> video_title)
        if "video_title" in data:
            db.update_project_setting(project_id, "title", data["video_title"])
            
        return {"status": "ok"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ===========================================
# API: 프로젝트 분석 및 기획
# ===========================================

@router.post("/{project_id}/analysis")
async def save_analysis(project_id: int, req: AnalysisSave, background_tasks: BackgroundTasks):
    """분석 결과 저장"""
    db.save_analysis(project_id, req.video_data, req.analysis_result)
    db.update_project(project_id, status="analyzed")
    
    # [NEW] 프로젝트 설정에서 스타일 가져오기 (기본값 story)
    settings = db.get_project_settings(project_id)
    script_style = settings.get('script_style', 'story') if settings else 'story'
    
    # [NEW] 성공 전략 학습 (백그라운드 실행)
    background_tasks.add_task(
        background_learn_strategy, 
        req.video_data.get('id'), 
        req.analysis_result,
        script_style
    )
    
    return {"status": "ok"}

@router.get("/{project_id}/analysis")
async def get_analysis(project_id: int):
    """분석 결과 조회"""
    return db.get_analysis(project_id) or {}

@router.post("/{project_id}/script-structure")
async def save_script_structure(project_id: int, req: ScriptStructureSave):
    """대본 구조 저장"""
    db.save_script_structure(project_id, req.dict())
    db.update_project(project_id, status="planned")
    return {"status": "ok"}

@router.get("/{project_id}/script-structure")
async def get_script_structure(project_id: int):
    """대본 구조 조회"""
    data = db.get_script_structure(project_id)
    return data or {}


@router.post("/{project_id}/script-structure/auto")
async def auto_generate_script_structure(project_id: int):
    """대본 구조 자동 생성 (분석 결과 기반)"""
    # 1. 분석 결과 조회
    analysis = db.get_analysis(project_id)
    if not analysis or not analysis.get("analysis_result"):
        raise HTTPException(400, "분석 데이터가 없습니다. 먼저 분석을 진행해주세요.")

    # [NEW] Accumulated Knowledge Load
    knowledge = []
    try:
        past_analyses = db.get_top_analyses(limit=5)
        import json
        for pa in past_analyses:
            try:
                res = pa['analysis_result']
                if isinstance(res, str): res = json.loads(res)
                
                # Extract Success Factors
                if 'success_analysis' in res and 'success_factors' in res['success_analysis']:
                    for factor in res['success_analysis']['success_factors']:
                         knowledge.append({
                             "category": "Viral Factor",
                             "pattern": factor.get('factor', 'Insight'),
                             "insight": factor.get('reason', '')
                         })
            except: continue
        if knowledge:
            print(f"DEBUG: Loaded {len(knowledge)} accumulated success insights from DB.")
    except Exception as e:
        print(f"Failed to load accumulated knowledge: {e}")

    # 2. Gemini를 사용하여 구조 생성 (with Knowledge)
    structure = await gemini_service.generate_script_structure(analysis["analysis_result"], accumulated_knowledge=knowledge)
    
    # 3. 저장
    db.save_script_structure(project_id, structure)
    db.update_project(project_id, status="planned")

    return {"status": "ok", "structure": structure}

# ===========================================
# API: 프로젝트 전체 데이터 로드 (핵심)
# ===========================================

@router.get("/{project_id}/full_data")
async def get_full_project_data(project_id: int):
    """
    프로젝트의 모든 데이터를 한 번에 조회합니다.
    (프로젝트 정보, 설정, 분석, 기획, 스크립트, 이미지 프롬프트 등)
    """
    try:
        project = db.get_project(project_id)
        if not project:
            raise HTTPException(404, "Project not found")
            
        settings = db.get_project_settings(project_id) or {}
        analysis = db.get_analysis(project_id) or {}
        structure = db.get_script_structure(project_id) or {}
        script_data = db.get_script(project_id) or {}
        image_prompts = db.get_image_prompts(project_id) or []
        tts_data = db.get_tts(project_id) or {}
        metadata = db.get_metadata(project_id) or {}
        
        # [NEW] App Mode Check (Default to 'longform' if not set)
        app_mode = settings.get('app_mode', 'longform')
        
        # Shorts specific data
        shorts_data = []
        if app_mode == 'shorts':
             # Load from shorts_data table/json
             # Assuming db.get_shorts_data exists or we store in script_structure?
             # Traditionally we don't have explicit shorts table yet, stored in structure or settings.
             # Based on main.py, shorts data is usually handled via specific endpoints or integrated.
             # For now return structure if it looks like shorts.
             pass

        return {
            "status": "ok",
            "project": project,
            "settings": settings,
            "analysis": analysis,
            "structure": structure,
            "script": script_data,
            "prompts": image_prompts,
            "tts": tts_data,
            "metadata": metadata,
            "app_mode": app_mode
        }
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(500, f"데이터 로드 실패: {e}")


# ===========================================
# API: 프로젝트 설정 (개별/일괄)
# ===========================================

class ProjectSettingUpdate(BaseModel):
    key: str
    value: Any

@router.patch("/{project_id}/settings/{key}")
async def patch_project_setting(project_id: int, key: str, req: ProjectSettingUpdate):
    """
    개별 프로젝트 설정 업데이트
    """
    # req.key와 url의 key가 다를 수 있지만, url 우선.
    db.update_project_setting(project_id, key, req.value)
    return {"status": "ok", "key": key, "value": req.value}

@router.post("/{project_id}/settings/bulk")
async def save_project_settings_bulk(project_id: int, settings: Dict[str, Any]):
    """일괄 설정 저장 (Bulk)"""
    db.save_project_settings(project_id, settings)
    return {"status": "ok"}
