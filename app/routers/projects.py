from fastapi import APIRouter, HTTPException, Body, Request
from typing import List, Optional
import database as db
from app.models.project import ProjectCreate, ProjectUpdate, ProjectSettingUpdate, ProjectSettingsSave

router = APIRouter(prefix="/api", tags=["Projects"])

@router.get("/projects")
async def get_projects():
    try:
        projects = db.get_projects()
        return {"status": "success", "projects": projects}
    except Exception as e:
        raise HTTPException(500, str(e))

@router.post("/projects")
async def create_project(data: ProjectCreate):
    try:
        project_id = db.create_project(data.name, data.topic, data.target_language)
        return {"status": "success", "project_id": project_id}
    except Exception as e:
        raise HTTPException(500, str(e))

@router.get("/projects/{project_id}")
async def get_project(project_id: int):
    project = db.get_project(project_id)
    if not project:
        raise HTTPException(404, "Project not found")
    return {"status": "success", "project": project}

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
