from typing import Dict, Optional

from fastapi import HTTPException

import database as db
from app.modes import DEFAULT_APP_MODE, normalize_app_mode
from services.auth_service import auth_service


def ensure_project_access(project_id: int, *, allow_unassigned: bool = True) -> Dict:
    project = db.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    email = (auth_service.get_user_email() or "").strip().lower()
    owner_email = (project.get("employee_email") or "").strip().lower()

    if email and db.is_user_admin(email):
        return project
    if email and owner_email and owner_email == email:
        return project
    if email and not owner_email and allow_unassigned:
        return project

    raise HTTPException(status_code=403, detail="Project access denied")


def resolve_project_mode(project_id: Optional[int] = None) -> str:
    if project_id:
        project = ensure_project_access(project_id)
        settings = db.get_project_settings(project_id) or {}
        project_mode = settings.get("app_mode") or project.get("app_mode")
        if project_mode:
            return normalize_app_mode(project_mode, DEFAULT_APP_MODE)
    return normalize_app_mode(db.get_global_setting("app_mode", DEFAULT_APP_MODE), DEFAULT_APP_MODE)
