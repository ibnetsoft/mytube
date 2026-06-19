import json
import os
import tempfile
from typing import Any, Dict, Optional

import database as db
from config import config
from services.google_drive_service import google_drive_service
from services.sync_service import _resolve_local_asset_path


def _get_drive_root_folder_id() -> str:
    try:
        config.load_remote_keys_from_supabase()
    except Exception:
        pass
    return (
        getattr(config, "REMOTE_RENDER_DRIVE_FOLDER_ID", "")
        or db.get_global_setting("remote_render_drive_folder_id", "")
        or ""
    )


def _get_drive_token_path() -> Optional[str]:
    try:
        config.load_remote_keys_from_supabase()
    except Exception:
        pass
    token_path = (
        getattr(config, "REMOTE_RENDER_GOOGLE_TOKEN_PATH", "")
        or db.get_global_setting("remote_render_google_token_path", "")
        or ""
    )
    if token_path and not os.path.isabs(token_path):
        token_path = os.path.join(config.BASE_DIR, token_path)
    return token_path or None


def _pick_drive_file(files, preferred_id: str, preferred_name: str, mime_prefix: str = "", fallback_exts=()):
    if preferred_id:
        by_id = next((item for item in files if item.get("id") == preferred_id), None)
        if by_id:
            return by_id
    if preferred_name:
        by_name = next((item for item in files if item.get("name") == preferred_name), None)
        if by_name:
            return by_name
    if mime_prefix:
        by_mime = next((item for item in files if str(item.get("mimeType") or "").startswith(mime_prefix)), None)
        if by_mime:
            return by_mime
    lowered_exts = tuple(ext.lower() for ext in fallback_exts)
    if lowered_exts:
        return next(
            (item for item in files if str(item.get("name") or "").lower().endswith(lowered_exts)),
            None,
        )
    return None


class DriveBundleService:
    def get_project_bundle(self, project_id: int) -> Dict[str, Any]:
        project = db.get_project(project_id) or {}
        settings = db.get_project_settings(project_id) or {}
        local_metadata = db.get_project_metadata(project_id, settings.get("app_mode")) or {}

        root_folder_id = _get_drive_root_folder_id()
        token_path = _get_drive_token_path()
        folder = None

        folder_id = settings.get("drive_project_folder_id")
        if folder_id:
            folder = google_drive_service.get_file_metadata(folder_id, token_path=token_path)

        if not folder and root_folder_id and project.get("employee_email") and project.get("name"):
            email_folder = google_drive_service.find_folder(
                project.get("employee_email"),
                token_path=token_path,
                parent_folder_id=root_folder_id,
            )
            if email_folder and email_folder.get("id"):
                folder = google_drive_service.find_folder(
                    project.get("name"),
                    token_path=token_path,
                    parent_folder_id=email_folder.get("id"),
                )

        files = google_drive_service.list_files(folder.get("id"), token_path=token_path) if folder and folder.get("id") else []

        metadata_file = _pick_drive_file(
            files,
            settings.get("drive_metadata_file_id"),
            settings.get("drive_metadata_file_name") or "metadata.json",
            fallback_exts=(".json",),
        )
        metadata_json = None
        if metadata_file and metadata_file.get("id"):
            raw = google_drive_service.read_text_file(metadata_file.get("id"), token_path=token_path)
            if raw:
                try:
                    metadata_json = json.loads(raw)
                except Exception:
                    metadata_json = None

        video_file = _pick_drive_file(
            files,
            settings.get("drive_video_file_id"),
            settings.get("drive_video_file_name"),
            mime_prefix="video/",
            fallback_exts=(".mp4", ".mov", ".avi", ".mkv", ".webm"),
        )
        thumbnail_file = _pick_drive_file(
            files,
            settings.get("drive_thumbnail_file_id"),
            settings.get("drive_thumbnail_file_name") or (metadata_json or {}).get("thumbnail_file"),
            mime_prefix="image/",
            fallback_exts=(".png", ".jpg", ".jpeg", ".webp"),
        )

        title = (
            (metadata_json or {}).get("title")
            or (local_metadata.get("titles") or [None])[0]
            or settings.get("title")
            or project.get("name")
            or f"Project {project_id}"
        )
        description = (
            (metadata_json or {}).get("description")
            or local_metadata.get("description")
            or settings.get("description")
            or ""
        )
        tags = (metadata_json or {}).get("tags") or local_metadata.get("tags") or []
        hashtags = (metadata_json or {}).get("hashtags") or local_metadata.get("hashtags") or []

        return {
            "project_id": project_id,
            "folder": folder,
            "video_file": video_file,
            "thumbnail_file": thumbnail_file,
            "metadata_file": metadata_file,
            "metadata_json": metadata_json,
            "title": title,
            "description": description,
            "tags": tags,
            "hashtags": hashtags,
            "track_count": (metadata_json or {}).get("track_count"),
            "track_durations": (metadata_json or {}).get("track_durations") or [],
            "total_duration_seconds": (metadata_json or {}).get("total_duration_seconds"),
            "status": "ok" if folder else "empty",
        }

    def prepare_youtube_upload_assets(self, project_id: int) -> Dict[str, Any]:
        bundle = self.get_project_bundle(project_id)
        token_path = _get_drive_token_path()
        folder = bundle.get("folder") or {}
        video_file = bundle.get("video_file") or {}
        if not video_file.get("id"):
            raise FileNotFoundError("Google Drive project bundle video not found.")

        temp_dir = tempfile.mkdtemp(prefix=f"drive_bundle_{project_id}_")
        video_filename = video_file.get("name") or f"project_{project_id}.mp4"
        video_path = os.path.join(temp_dir, video_filename)
        downloaded_video = google_drive_service.download_file(video_file.get("id"), video_path, token_path=token_path)
        if not downloaded_video or not os.path.exists(downloaded_video):
            raise FileNotFoundError("Failed to download Drive video file.")

        thumbnail_path = None
        thumbnail_file = bundle.get("thumbnail_file") or {}
        if thumbnail_file.get("id"):
            thumb_name = thumbnail_file.get("name") or "thumbnail.png"
            thumbnail_path = os.path.join(temp_dir, thumb_name)
            downloaded_thumb = google_drive_service.download_file(
                thumbnail_file.get("id"),
                thumbnail_path,
                token_path=token_path,
            )
            if not downloaded_thumb or not os.path.exists(downloaded_thumb):
                thumbnail_path = None

        if not thumbnail_path:
            local_thumb = _resolve_local_asset_path(
                (bundle.get("metadata_json") or {}).get("thumbnail_url")
                or (db.get_project_settings(project_id) or {}).get("thumbnail_url")
                or (db.get_project_settings(project_id) or {}).get("thumbnail_path")
            )
            if local_thumb and os.path.exists(local_thumb):
                thumbnail_path = local_thumb

        return {
            "temp_dir": temp_dir,
            "folder": folder,
            "video_path": downloaded_video,
            "thumbnail_path": thumbnail_path,
            "title": bundle.get("title"),
            "description": bundle.get("description"),
            "tags": bundle.get("tags") or [],
            "hashtags": bundle.get("hashtags") or [],
            "metadata_json": bundle.get("metadata_json") or {},
        }


drive_bundle_service = DriveBundleService()
