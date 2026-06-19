import json
import os
import shutil
from typing import Any, Dict, Optional

import database as db
from config import config
from services.drive_bundle_service import drive_bundle_service
from services.sync_service import upsert_web_admin_publishing_request
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
    preferred_handle = (settings.get("preferred_youtube_channel_handle") or "").strip()
    try:
        target_chan_id = requested_channel_id or settings.get("youtube_channel_id")
        if not target_chan_id:
            if preferred_handle:
                preferred_channel = db.get_channel_by_handle(preferred_handle)
                if preferred_channel and preferred_channel.get("id"):
                    target_chan_id = preferred_channel["id"]
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

        if not token_path and not preferred_handle:
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
        metadata = db.get_project_metadata(project_id, settings.get("app_mode")) or {}

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
        preferred_handle = (settings.get("preferred_youtube_channel_handle") or "").strip()
        if preferred_handle and not token_path:
            preferred_name = settings.get("preferred_youtube_channel_name") or preferred_handle
            raise RuntimeError(f"Fixed upload channel is not connected locally: {preferred_name}")
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


def queue_project_for_admin_publish(
    project_id: int,
    *,
    requested_privacy: str = "private",
    requested_publish_at: Optional[str] = None,
    requested_channel_id: Optional[int] = None,
) -> Dict[str, Any]:
    project = db.get_project(project_id)
    if not project:
        raise FileNotFoundError(f"Project not found: {project_id}")

    settings = db.get_project_settings(project_id) or {}
    bundle = drive_bundle_service.get_project_bundle(project_id)
    video_file = bundle.get("video_file") or {}
    folder = bundle.get("folder") or {}
    thumbnail_file = bundle.get("thumbnail_file") or {}
    metadata_file = bundle.get("metadata_file") or {}

    if not video_file.get("id"):
        raise FileNotFoundError("Google Drive bundle video not found for this project.")

    title = bundle.get("title") or project.get("name") or f"Project {project_id}"
    description = bundle.get("description") or ""
    tags = list(bundle.get("tags") or [])
    hashtags = list(bundle.get("hashtags") or [])
    metadata_json = bundle.get("metadata_json") or {}
    track_count = metadata_json.get("track_count")
    total_duration_seconds = metadata_json.get("total_duration_seconds")
    track_durations = metadata_json.get("track_durations") or []
    if not track_count or not track_durations or not total_duration_seconds:
        try:
            queue_payload = json.loads(settings.get("remote_render_queue_payload") or "{}")
        except Exception:
            queue_payload = {}
        queue_metadata = queue_payload.get("metadata") or {}
        track_count = track_count or queue_metadata.get("track_count")
        track_durations = track_durations or queue_metadata.get("track_durations") or []
        total_duration_seconds = total_duration_seconds or queue_metadata.get("total_duration_seconds")
    if total_duration_seconds in (None, "", 0) and isinstance(track_durations, list):
        try:
            total_duration_seconds = sum(int(item or 0) for item in track_durations)
        except Exception:
            total_duration_seconds = None

    db.update_project_setting(project_id, "upload_privacy", requested_privacy or "private")
    db.update_project_setting(project_id, "upload_schedule_at", requested_publish_at)
    if requested_channel_id is not None:
        db.update_project_setting(project_id, "youtube_channel_id", requested_channel_id)

    payload_metadata = {
        "title": title,
        "description": description,
        "tags": tags,
        "hashtags": hashtags,
        "drive_folder_id": folder.get("id"),
        "drive_video_file_id": video_file.get("id"),
        "drive_thumbnail_file_id": thumbnail_file.get("id"),
        "drive_metadata_file_id": metadata_file.get("id"),
        "channel_id": requested_channel_id or settings.get("youtube_channel_id"),
        "preferred_channel_handle": settings.get("preferred_youtube_channel_handle"),
        "preferred_channel_name": settings.get("preferred_youtube_channel_name"),
        "privacy_status": requested_privacy or "private",
        "publish_at": requested_publish_at,
        "track_count": track_count,
        "track_durations": track_durations,
        "total_duration_seconds": total_duration_seconds,
        "app_mode": settings.get("app_mode") or "longform_music",
    }
    response = upsert_web_admin_publishing_request(
        project_id,
        video_url=video_file.get("webViewLink"),
        status="pending",
        metadata_payload=payload_metadata,
    )
    if response is None or response.status_code not in (200, 201, 204):
        raise RuntimeError("Failed to register project in web-admin publishing queue.")

    db.update_project_setting(project_id, "admin_publish_ready", "1")
    db.update_project_setting(project_id, "admin_publish_status", "pending_review")
    db.update_project_setting(project_id, "is_uploaded", 1)

    return {
        "status": "ok",
        "project_id": project_id,
        "queue_status": "pending_review",
        "video_url": video_file.get("webViewLink"),
        "url": video_file.get("webViewLink"),
        "title": title,
        "description": description,
        "hashtags": hashtags,
        "publish_at": requested_publish_at,
    }
