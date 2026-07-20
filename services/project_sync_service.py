"""Best-effort Supabase sync for desktop project text metadata.

Media files remain local. This service mirrors project text/config snapshots to
Supabase via the desktop-project-sync auth-web bridge.

[AIR-0225B] Used to call web_admin_client.supabase_get/upsert_by_key directly
with SUPABASE_SERVICE_ROLE_KEY. That key was removed from packaged desktop
builds, so has_supabase() has silently returned False in every build since -
fetch_remote_projects()/ensure_local_projects_from_remote() quietly no-opped
on every call, with no error surfaced anywhere. A fresh install (or any
machine whose local SQLite lost a project row) showed an empty project list
even though the row was sitting in Supabase. Migrated to the same
email + HMAC session_token bridge pattern as referral.py/support.py.
"""
import datetime
import json
import os
import re
from typing import Any, Dict, Optional

import database as db
from services.web_admin_client import web_admin_client


_PATH_KEY_RE = re.compile(r"(path|url|file|image|video|audio|thumbnail)", re.IGNORECASE)


def _bridge(action: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    from services.auth_service import auth_service
    email = auth_service.get_user_email()
    session_token = auth_service.get_session_token()
    if not email or not session_token:
        return {"success": False, "error": "not_logged_in"}
    return web_admin_client.desktop_project_sync(email, session_token, action, params)


def _utc_now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def _is_local_media_value(value: str) -> bool:
    if not value:
        return False
    lowered = value.lower()
    return (
        ":\\" in value
        or ":/" in value
        or lowered.startswith("/output/")
        or lowered.startswith("output/")
        or lowered.startswith("/uploads/")
        or lowered.startswith("uploads/")
        or "appdata" in lowered
        or "picadilly" in lowered and any(ext in lowered for ext in (".png", ".jpg", ".jpeg", ".mp4", ".mp3", ".wav", ".srt"))
    )


def _sanitize(value: Any, key: str = "") -> Any:
    if isinstance(value, dict):
        return {k: _sanitize(v, k) for k, v in value.items()}
    if isinstance(value, list):
        return [_sanitize(v, key) for v in value]
    if isinstance(value, tuple):
        return [_sanitize(v, key) for v in value]
    if isinstance(value, bytes):
        return None
    if isinstance(value, str):
        if _PATH_KEY_RE.search(key or "") and _is_local_media_value(value):
            return {"local_media_ref": True, "basename": os.path.basename(value.replace("\\", "/"))}
        return value
    return value


def _project_app_mode(full_data: Dict[str, Any]) -> str:
    settings = full_data.get("settings") or {}
    return settings.get("app_mode") or "longform"


def build_project_payload(project_id: int) -> Optional[Dict[str, Any]]:
    full_data = db.get_project_full_data_v2(project_id)
    if not full_data:
        return None

    media_summary = {}
    settings = full_data.get("settings") or {}
    images = full_data.get("image_prompts") or []
    media_summary["image_count"] = sum(1 for item in images if item.get("image_url"))
    media_summary["video_scene_count"] = sum(1 for item in images if item.get("video_url"))
    media_summary["has_project_video"] = bool(settings.get("video_path") or settings.get("external_video_path"))
    media_summary["has_tts_audio"] = bool(full_data.get("tts"))
    media_summary["has_thumbnail"] = bool(settings.get("thumbnail_url") or full_data.get("thumbnails"))

    payload = {
        "version": 1,
        "project": full_data.get("project"),
        "settings": full_data.get("settings"),
        "analysis": full_data.get("analysis"),
        "script_structure": full_data.get("script_structure"),
        "script": full_data.get("script"),
        "image_prompts": full_data.get("image_prompts"),
        "tts": full_data.get("tts"),
        "metadata": full_data.get("metadata"),
        "thumbnails": full_data.get("thumbnails"),
        "shorts": full_data.get("shorts"),
        "characters": full_data.get("characters"),
        "local_media": media_summary,
    }
    return _sanitize(payload)


def sync_project_metadata(project_id: int, employee_email: str = "") -> bool:
    project = db.get_project(project_id)
    if not project:
        return False

    payload = build_project_payload(project_id)
    if payload is None:
        return False

    full_data = db.get_project_full_data_v2(project_id) or {}
    progress_payload = {}
    try:
        from services.topic_queue_sync_service import build_project_progress_snapshot
        progress_payload = build_project_progress_snapshot(project_id)
    except Exception as e:
        print(f"[ProjectSync] Progress snapshot warning for {project_id}: {e}")

    now = _utc_now()
    sync_id = project.get("sync_id")
    if not sync_id:
        db.mark_project_dirty(project_id)
        return False

    result = _bridge("push", {
        "sync_id": sync_id,
        "local_project_id": project_id,
        "name": project.get("name") or "",
        "topic": project.get("topic") or "",
        "status": project.get("status") or "draft",
        "language": project.get("language") or "ko",
        "app_mode": _project_app_mode(full_data),
        "project_payload": payload,
        "progress_payload": progress_payload,
        "deleted_at": project.get("remote_deleted_at"),
    })

    if result.get("success"):
        db.mark_project_synced(project_id, now)
        return True
    db.mark_project_dirty(project_id)
    if result.get("error") != "not_logged_in":
        print(f"[ProjectSync] Failed to sync project {project_id}: {result.get('error')}")
    return False


def sync_project_deleted(project: Dict[str, Any]) -> bool:
    if not project or not project.get("sync_id"):
        return False
    result = _bridge("soft_delete", {
        "sync_id": project["sync_id"],
        "local_project_id": project.get("id"),
        "name": project.get("name") or "",
        "topic": project.get("topic") or "",
    })
    if not result.get("success") and result.get("error") != "not_logged_in":
        print(f"[ProjectSync] Failed to soft-delete remote project {project.get('id')}: {result.get('error')}")
    return bool(result.get("success"))


def sync_dirty_projects(employee_email: str = "", limit: int = 20) -> Dict[str, int]:
    projects = db.get_dirty_projects(employee_email=employee_email or None, limit=limit)
    result = {"attempted": 0, "synced": 0, "failed": 0}
    for project in projects:
        pid = project.get("id")
        if not pid:
            continue
        result["attempted"] += 1
        if sync_project_metadata(pid, employee_email=employee_email or project.get("employee_email") or ""):
            result["synced"] += 1
        else:
            result["failed"] += 1
    if result["attempted"]:
        print(f"[ProjectSync] Dirty sync result: {json.dumps(result, ensure_ascii=False)}")
    return result


def fetch_remote_projects(employee_email: str) -> list:
    """Supabase에서 사용자의 프로젝트 목록을 가져옵니다 (project_payload 포함 -
    복원 시 설정값까지 함께 복원하려면 필요. 예전 코드는 select에서
    project_payload를 빼먹어 복원돼도 항상 빈 설정으로 생성되는 별개의
    잠재 버그가 있었다 - 브릿지로 옮기며 같이 고쳤다)."""
    if not employee_email:
        return []

    result = _bridge("list")
    if not result.get("success"):
        if result.get("error") != "not_logged_in":
            print(f"[ProjectSync] Failed to fetch remote projects: {result.get('error')}")
        return []
    return result.get("projects") or []


def ensure_local_projects_from_remote(employee_email: str) -> Dict[str, int]:
    """Supabase에 있는 프로젝트가 로컬에 없으면 복원합니다.

    Returns:
        Dict with 'fetched', 'restored', 'skipped', 'failed' counts
    """
    if not employee_email:
        return {"fetched": 0, "restored": 0, "skipped": 0, "failed": 0}

    result = {"fetched": 0, "restored": 0, "skipped": 0, "failed": 0}

    try:
        # 1. 원격 프로젝트 목록 가져오기
        remote_projects = fetch_remote_projects(employee_email)
        result["fetched"] = len(remote_projects)

        if not remote_projects:
            return result

        # 2. 로컬에 이미 있는 sync_id 목록 확인
        local_projects = db.get_projects_with_status(employee_email=employee_email) or []
        local_sync_ids = {p.get("sync_id") for p in local_projects if p.get("sync_id")}

        # 3. 복원 필요한 프로젝트 필터링
        to_restore = [
            rp for rp in remote_projects
            if rp.get("sync_id") and rp.get("sync_id") not in local_sync_ids
        ]

        if not to_restore:
            return result

        print(f"[ProjectSync] Found {len(to_restore)} projects to restore from Supabase")

        # 4. 각 프로젝트 복원
        for rp in to_restore:
            sync_id = rp.get("sync_id")
            try:
                restored_id = restore_project_from_remote(rp)
                if restored_id:
                    result["restored"] += 1
                    print(f"[ProjectSync] Restored project: {rp.get('name')} (ID: {restored_id})")
                else:
                    result["failed"] += 1
                    print(f"[ProjectSync] Failed to restore project: {rp.get('name')}")
            except Exception as e:
                result["failed"] += 1
                print(f"[ProjectSync] Error restoring project {rp.get('name')}: {e}")

        return result

    except Exception as e:
        print(f"[ProjectSync] Error in ensure_local_projects_from_remote: {e}")
        result["failed"] = result.get("fetched", 0)
        return result


def restore_project_from_remote(remote_project: Dict[str, Any]) -> Optional[int]:
    """Supabase 프로젝트 데이터를 로컬 DB에 복원합니다.

    Returns:
        새로 생성된 로컬 project_id, 실패 시 None
    """
    sync_id = remote_project.get("sync_id")
    if not sync_id:
        return None

    # 이미 존재하는지 확인
    existing = db.get_project_by_sync_id(sync_id)
    if existing:
        return existing.get("id")

    # 로컬에 없으면 새 프로젝트 생성
    try:
        project_id = db.create_project(
            name=remote_project.get("name") or "Restored Project",
            topic=remote_project.get("topic") or "",
            app_mode=remote_project.get("app_mode") or "longform",
            language=remote_project.get("language") or "ko",
            employee_email=remote_project.get("employee_email"),
            sync_id=sync_id  # sync_id 유지
        )

        # 상태 업데이트
        status = remote_project.get("status") or "draft"
        if status:
            db.update_project(project_id, status=status)

        # project_payload에서 설정값 복원 (선택 사항)
        project_payload = remote_project.get("project_payload") or {}
        settings = project_payload.get("settings") or {}
        if settings:
            db.save_project_settings(project_id, settings)

        return project_id

    except Exception as e:
        print(f"[ProjectSync] Failed to restore project {sync_id}: {e}")
        return None
