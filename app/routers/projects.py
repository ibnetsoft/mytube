from fastapi import APIRouter, HTTPException, Body, Request
from typing import List, Optional
import database as db
from app.models.project import ProjectCreate, ProjectUpdate, ProjectSettingUpdate, ProjectSettingsSave

router = APIRouter(prefix="/api", tags=["Projects"])

@router.get("/projects")
async def get_projects():
    try:
        projects = db.get_projects_with_status()
        return {"status": "success", "projects": projects}
    except Exception as e:
        raise HTTPException(500, str(e))

@router.post("/projects")
async def create_project(request: Request):
    try:
        # Pydantic 모델 대신 원본 JSON을 직접 읽어서 매핑 오류 원천 차단
        data = await request.json()
        
        name = data.get("name", "Untitled")
        topic = data.get("topic")
        
        # 명시적으로 필드 추출
        target_lang = data.get("target_language") or data.get("language") or "ko"
        app_mode = data.get("app_mode") or data.get("mode") or "longform"
        
        # [ROBUST] 만약 app_mode에 언어 코드가 들어왔다면 보정 (매핑 오류 대비)
        if app_mode in ['ko', 'en', 'ja', 'vi', 'es']:
            # 언어가 모드로 잘못 들어온 경우:
            # 1. target_lang이 'ko'라면 app_mode가 진짜 데이터였을 수 있음
            # 2. 하지만 필드명이 'app_mode'인데 'ko'가 들어왔다면 보통 뒤바뀐 것
            real_mode = data.get("target_language") # target_language 필드에 shorts가 있었을 가능성
            if real_mode in ['shorts', 'longform']:
                app_mode = real_mode
                target_lang = data.get("app_mode") # 원래 언어
            else:
                app_mode = "longform" # 기본값 복구
        
        project_id = db.create_project(
            name=name, 
            topic=topic, 
            app_mode=app_mode, 
            language=target_lang
        )
        return {"status": "success", "project_id": project_id}
    except Exception as e:
        raise HTTPException(500, str(e))

@router.get("/projects/{project_id}")
async def get_project(project_id: int):
    project = db.get_project(project_id)
    if not project:
        raise HTTPException(404, "Project not found")
    return project

@router.put("/projects/{project_id}")
async def update_project(project_id: int, data: ProjectUpdate):
    try:
        db.update_project(project_id, data.name, data.topic, data.status)
        return {"status": "success"}
    except Exception as e:
        raise HTTPException(500, str(e))

@router.delete("/projects/{project_id}")
async def delete_project(project_id: int):
    try:
        db.delete_project(project_id)
        return {"status": "success"}
    except Exception as e:
        raise HTTPException(500, str(e))

@router.post("/project-settings/{project_id}")
async def save_project_settings(project_id: int, settings: ProjectSettingsSave):
    try:
        db.save_project_settings(project_id, settings.dict(exclude_unset=True))
        return {"status": "success"}
    except Exception as e:
        raise HTTPException(500, str(e))

@router.put("/project-settings/{project_id}")
async def update_project_setting(project_id: int, data: ProjectSettingUpdate):
    try:
        db.update_project_setting(project_id, data.key, data.value)
        return {"status": "success"}
    except Exception as e:
        raise HTTPException(500, str(e))
