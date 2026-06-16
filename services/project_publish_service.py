import os
import shutil
from typing import Any, Dict, Optional

import database as db
from config import config
from services.drive_bundle_service import drive_bundle_service
from services.youtube_upload_service import youtube_upload_service


def _resolve_local_output_asset_path(asset_url_or_path: Optional[str]) -> Optional[str]:
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


def _resolve_youtube_token_path(
    settings: Dict[str, Any],
    requested_channel_id: Optional[int] = None,
) -> Optional[str]:
    token_path = None
    try:
        target_chan_id = requested_channel_id or settings.get("youtube_channel_id")
        if target_chan_id:
            channel = db.get_channel(target_chan_id)
            if channel and channel.get("credentials_path"):
                cand_path = channel["credentials_path"]
                if not os.path.isabs(cand_path):
                    cand_path = os.path.join(config.BASE_DIR, cand_path)
                if os.path.exists(cand_path):
                    token_path = cand_path
                else:
                    rec_filename = f"token_{target_chan_id}.pickle"
                    rec_path = os.path.join(config.BASE_DIR, "tokens", rec_filename)
                    if os.path.exists(rec_path):
                        token_path = rec_path
                        print(f"[YouTube] Recovered token path from tokens directory: {token_path}")

        if not token_path:
            channels = db.get_all_channels()
            for ch in channels or []:
                c_path = ch.get("credentials_path")
                if not c_path:
                    continue
                if not os.path.isabs(c_path):
                    c_path = os.path.join(config.BASE_DIR, c_path)
                if os.path.exists(c_path):
                    token_path = c_path
                    break
    except Exception as e:
        print(f"[YouTube] Channel resolution error: {e}")
        token_path = None
    return token_path


def _resolve_project_thumbnail_path(settings: Dict[str, Any]) -> Optional[str]:
    thumb_candidate = settings.get("thumbnail_path") or settings.get("thumbnail_url")
    return _resolve_local_output_asset_path(thumb_candidate)


def publish_project_to_youtube(
    project_id: int,
    *,
    requested_privacy: str = "private",
    requested_publish_at: Optional[str] = None,
    requested_channel_id: Optional[int] = None,
) -> Dict[str, Any]:
    temp_dir_to_cleanup = None
    try:
        project = db.get_project(project_id)
        if not project:
            raise FileNotFoundError(f"Project not found: {project_id}")

        settings = db.get_project_settings(project_id) or {}
        metadata = db.get_metadata(project_id) or {}

        video_path = _resolve_local_output_asset_path(settings.get("external_video_path"))
        upload_source = "external"

        if not video_path:
            video_path = _resolve_local_output_asset_path(settings.get("video_path"))
            if video_path:
                upload_source = "rendered_local"

        drive_assets = None
        if not video_path:
            drive_assets = drive_bundle_service.prepare_youtube_upload_assets(project_id)
            temp_dir_to_cleanup = drive_assets.get("temp_dir")
            video_path = drive_assets.get("video_path")
            upload_source = "drive_bundle"

        if not video_path or not os.path.exists(video_path):
            raise FileNotFoundError(f"Uploadable video file not found for project {project_id}")

        if drive_assets:
            title = drive_assets.get("title") or project.get("name") or f"Project {project_id}"
            description = drive_assets.get("description") or ""
            tags = list(drive_assets.get("tags") or [])
            hashtags = list(drive_assets.get("hashtags") or [])
            thumbnail_path = drive_assets.get("thumbnail_path")
        else:
            title = (metadata.get("titles") or [project.get("name")])[0]
            description = metadata.get("description") or settings.get("description") or ""
            tags = list(metadata.get("tags") or [])
            hashtags = list(metadata.get("hashtags") or [])
            thumbnail_path = _resolve_project_thumbnail_path(settings)

        merged_tags = []
        for item in tags + hashtags:
            cleaned = str(item or "").strip()
            if cleaned and cleaned not in merged_tags:
                merged_tags.append(cleaned)

        token_path = _resolve_youtube_token_path(settings, requested_channel_id)
        result = youtube_upload_service.upload_video(
            file_path=video_path,
            title=title,
            description=description,
            tags=merged_tags[:15],
            category_id="22",
            privacy_status=requested_privacy,
            publish_at=requested_publish_at,
            token_path=token_path,
        )

        if not result or not result.get("id"):
            raise RuntimeError((result or {}).get("error", "YouTube upload failed"))

        video_id = result["id"]

        if thumbnail_path and os.path.exists(thumbnail_path):
            try:
                youtube_upload_service.set_thumbnail(
                    video_id=video_id,
                    thumbnail_path=thumbnail_path,
                    token_path=token_path,
                )
            except Exception as thumb_err:
                print(f"[YouTube] Thumbnail set skipped: {thumb_err}")

        db.update_project_setting(project_id, "youtube_video_id", video_id)
        db.update_project_setting(project_id, "is_published", 1)
        db.update_project_setting(project_id, "is_uploaded", 1)
        db.update_project_setting(project_id, "upload_source", upload_source)

        return {
            "status": "ok",
            "project_id": project_id,
            "video_id": video_id,
            "url": f"https://www.youtube.com/watch?v={video_id}",
            "upload_source": upload_source,
            "title": title,
            "description": description,
            "tags": merged_tags[:15],
        }
    finally:
        if temp_dir_to_cleanup and os.path.isdir(temp_dir_to_cleanup):
            try:
                shutil.rmtree(temp_dir_to_cleanup, ignore_errors=True)
            except Exception:
                pass
