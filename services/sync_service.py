import json
import os
import tempfile
import threading
from typing import Optional

import database as db
from config import config
from services.auth_service import auth_service
from services.google_drive_service import google_drive_service
from services.web_admin_client import web_admin_client


def _resolve_local_asset_path(asset_url_or_path: Optional[str]) -> Optional[str]:
    if not asset_url_or_path:
        return None
    if os.path.isabs(asset_url_or_path) and os.path.exists(asset_url_or_path):
        return asset_url_or_path
    if asset_url_or_path.startswith("/output/"):
        rel = asset_url_or_path.replace("/output/", "", 1).replace("/", os.sep)
        path = os.path.join(config.OUTPUT_DIR, rel)
        return path if os.path.exists(path) else None
    if asset_url_or_path.startswith("/static/"):
        rel = asset_url_or_path.replace("/static/", "", 1).replace("/", os.sep)
        path = os.path.join(config.STATIC_DIR, rel)
        return path if os.path.exists(path) else None
    if os.path.exists(asset_url_or_path):
        return asset_url_or_path
    return None


def _build_project_drive_metadata(project_id: int, video_file_name: str, thumbnail_file_name: Optional[str]):
    project = db.get_project(project_id) or {}
    settings = db.get_project_settings(project_id) or {}
    metadata = db.get_metadata(project_id) or {}

    title = (
        (metadata.get("titles") or [None])[0]
        or settings.get("title")
        or project.get("name")
        or f"Project {project_id}"
    )
    description = metadata.get("description") or settings.get("description") or ""
    tags = metadata.get("tags") or []
    hashtags = metadata.get("hashtags") or [
        item.strip() for item in str(settings.get("hashtags") or "").split(",") if item.strip()
    ]

    return {
        "project_id": project_id,
        "project_name": project.get("name") or f"Project {project_id}",
        "topic": project.get("topic") or "",
        "employee_email": project.get("employee_email") or auth_service.get_user_email() or "",
        "title": title,
        "description": description,
        "tags": tags,
        "hashtags": hashtags,
        "video_file": video_file_name,
        "thumbnail_file": thumbnail_file_name,
        "thumbnail_url": settings.get("thumbnail_url") or "",
        "video_path": settings.get("video_path") or "",
        "status": "ready_for_upload",
        "app_mode": settings.get("app_mode") or db.get_global_setting("app_mode", "longform"),
    }


def _get_drive_root_folder_id():
    try:
        config.load_remote_keys_from_supabase()
    except Exception:
        pass
    return getattr(config, "REMOTE_RENDER_DRIVE_FOLDER_ID", "") or db.get_global_setting("remote_render_drive_folder_id", "")


def upload_and_sync_video(project_id: int, local_video_path: str):
    """Upload project deliverables to Google Drive and keep a lightweight admin index row."""
    try:
        project = db.get_project(project_id)
        if not project:
            print(f"[Sync] Project {project_id} not found")
            return

        settings = db.get_project_settings(project_id) or {}
        email = project.get("employee_email") or auth_service.get_user_email()
        if not email:
            print("[Sync] No email associated with project/session")
            return

        root_folder_id = _get_drive_root_folder_id() or None
        project_folder = google_drive_service.ensure_project_folder(
            email=email,
            project_name=project.get("name") or f"Project {project_id}",
            token_path=None,
            root_folder_id=root_folder_id,
        )
        if not project_folder or not project_folder.get("id"):
            print("[Sync] Failed to create/find Drive project folder")
            return

        print(f"[Sync] Uploading project bundle to Google Drive folder {project_folder.get('name')}...")

        video_filename = os.path.basename(local_video_path)
        video_file = google_drive_service.upsert_file(
            local_video_path,
            folder_id=project_folder.get("id"),
            filename=video_filename,
            mimetype="video/mp4",
            description=f"Picadiri rendered video for project {project_id}",
            make_public=False,
        )
        if not video_file:
            print("[Sync] Google Drive video upload failed")
            return

        thumbnail_path = _resolve_local_asset_path(settings.get("thumbnail_url") or settings.get("thumbnail_path"))
        thumbnail_file = None
        thumbnail_file_name = None
        if thumbnail_path and os.path.exists(thumbnail_path):
            ext = os.path.splitext(thumbnail_path)[1] or ".png"
            thumbnail_file_name = f"thumbnail{ext.lower()}"
            thumbnail_file = google_drive_service.upsert_file(
                thumbnail_path,
                folder_id=project_folder.get("id"),
                filename=thumbnail_file_name,
                mimetype=f"image/{ext.lower().lstrip('.')}" if ext.lower() != ".jpg" else "image/jpeg",
                description=f"Picadiri thumbnail for project {project_id}",
                make_public=False,
            )

        metadata_payload = _build_project_drive_metadata(project_id, video_filename, thumbnail_file_name)
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as tmp:
            json.dump(metadata_payload, tmp, ensure_ascii=False, indent=2)
            metadata_tmp_path = tmp.name
        try:
            metadata_file = google_drive_service.upsert_file(
                metadata_tmp_path,
                folder_id=project_folder.get("id"),
                filename="metadata.json",
                mimetype="application/json",
                description=f"Picadiri metadata for project {project_id}",
                make_public=False,
            )
        finally:
            try:
                os.remove(metadata_tmp_path)
            except Exception:
                pass

        db.update_project_setting(project_id, "drive_project_folder_id", project_folder.get("id"))
        db.update_project_setting(project_id, "drive_project_folder_name", project_folder.get("name"))
        db.update_project_setting(project_id, "drive_video_file_id", (video_file or {}).get("id"))
        db.update_project_setting(project_id, "drive_video_file_name", (video_file or {}).get("name"))
        db.update_project_setting(project_id, "drive_thumbnail_file_id", (thumbnail_file or {}).get("id") if thumbnail_file else None)
        db.update_project_setting(project_id, "drive_thumbnail_file_name", thumbnail_file_name)
        db.update_project_setting(project_id, "drive_metadata_file_id", (metadata_file or {}).get("id") if metadata_file else None)
        db.update_project_setting(project_id, "drive_metadata_file_name", "metadata.json")

        print(f"[Sync] Google Drive project bundle uploaded: folder={project_folder.get('name')}")

        user_id = web_admin_client.resolve_user_id(email=email)
        if user_id:
            metadata_payload = {
                "project_id": project_id,
                "project_name": project.get("name"),
                "topic": project.get("topic"),
                "title": metadata_payload["title"],
                "description": metadata_payload["description"],
                "tags": metadata_payload["tags"],
                "hashtags": metadata_payload["hashtags"],
                "employee_email": email,
                "drive_folder_id": project_folder.get("id"),
                "drive_video_file_id": (video_file or {}).get("id"),
                "drive_thumbnail_file_id": (thumbnail_file or {}).get("id") if thumbnail_file else None,
                "drive_metadata_file_id": (metadata_file or {}).get("id") if metadata_file else None,
            }
            payload = {
                "user_id": user_id,
                "video_url": (video_file or {}).get("webViewLink"),
                "metadata": metadata_payload,
                "status": "pending",
            }
            existing = web_admin_client.supabase_get(
                "publishing_requests",
                params={
                    "select": "id,status,metadata",
                    "user_id": f"eq.{user_id}",
                    "status": "in.(pending,to_be_published,failed)",
                },
                timeout=10,
            )
            existing_row = None
            if existing is not None and existing.status_code == 200:
                for row in existing.json() or []:
                    if (row.get("metadata") or {}).get("project_id") == project_id:
                        existing_row = row
                        break

            if existing_row:
                r_publish = web_admin_client.supabase_patch(
                    "publishing_requests",
                    payload,
                    params={"id": f"eq.{existing_row.get('id')}"},
                    timeout=10,
                )
            else:
                r_publish = web_admin_client.supabase_post("publishing_requests", payload, timeout=10)

            if r_publish is not None and r_publish.status_code in [200, 201, 204]:
                print("[Sync] Lightweight admin index row synced to Supabase.")

        db.update_project_setting(project_id, "is_uploaded", 1)
    except Exception as e:
        print(f"[Sync Error] Failed to upload/sync: {e}")


def start_upload_and_sync_background(project_id: int, local_video_path: str):
    """Start Drive bundle upload/sync in a background thread."""
    threading.Thread(
        target=upload_and_sync_video,
        args=(project_id, local_video_path),
        daemon=True,
    ).start()
