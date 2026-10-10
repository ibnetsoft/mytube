"""Learning log service for the YouTube production pipeline.

Stage 1 stores structured events and project snapshots so future
recommendation/RAG/analytics features can learn from actual production work.
All functions are best-effort: learning failures must never block creation,
rendering, review, or upload flows.
"""

from __future__ import annotations

import json
import threading
from typing import Any, Dict, Optional

import database as db


def _loads(value: Any, fallback: Any = None) -> Any:
    if fallback is None:
        fallback = {}
    if value in (None, ""):
        return fallback
    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(value)
    except Exception:
        return fallback


def _safe_call(fn, default=None):
    try:
        return fn()
    except Exception as exc:
        print(f"[Learning] Context collection skipped part: {exc}")
        return default


def build_reference_summary(settings: Dict[str, Any]) -> Dict[str, Any]:
    samples = _loads(settings.get("youtube_reference_samples_json"), [])
    selected_key = settings.get("thumbnail_reference_sample_key") or ""
    selected = None
    if isinstance(samples, list) and selected_key:
        for item in samples:
            if not isinstance(item, dict):
                continue
            key = item.get("key") or item.get("video_id") or item.get("thumbnail_url") or item.get("url")
            if str(key) == str(selected_key):
                selected = item
                break
    return {
        "selected_key": selected_key,
        "selected": selected or {},
        "sample_count": len(samples) if isinstance(samples, list) else 0,
        "samples": samples if isinstance(samples, list) else [],
    }


def build_style_summary(settings: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "script_style": settings.get("script_style") or "",
        "image_style": settings.get("image_style") or "",
        "thumbnail_style": settings.get("thumbnail_style") or "",
        "subtitle_style": settings.get("subtitle_style_enum") or "",
        "app_mode": settings.get("app_mode") or "longform",
        "creation_mode": settings.get("creation_mode") or "default",
    }


def collect_project_learning_context(project_id: int) -> Dict[str, Any]:
    project = _safe_call(lambda: db.get_project(project_id), {}) or {}
    settings = _safe_call(lambda: db.get_project_settings(project_id), {}) or {}
    script = _safe_call(lambda: db.get_script(project_id), {}) or {}
    thumbnails = _safe_call(lambda: db.get_thumbnails(project_id), {}) or {}
    metadata = _safe_call(lambda: db.get_metadata(project_id), {}) or {}

    return {
        "project": {
            "id": project_id,
            "name": project.get("name") or "",
            "topic": project.get("topic") or "",
            "status": project.get("status") or "",
            "target_language": settings.get("target_language") or project.get("target_language") or "ko",
            "title": settings.get("title") or metadata.get("titles", [""])[0] if isinstance(metadata.get("titles"), list) and metadata.get("titles") else settings.get("title") or "",
            "app_mode": settings.get("app_mode") or "longform",
        },
        "reference": build_reference_summary(settings),
        "style": build_style_summary(settings),
        "script": {
            "style": settings.get("script_style") or "",
            "length": len(script.get("full_script") or settings.get("script") or ""),
            "word_count": script.get("word_count") or 0,
            "estimated_duration": script.get("estimated_duration") or 0,
            "language": script.get("language") or settings.get("target_language") or "",
        },
        "thumbnail": {
            "style": settings.get("thumbnail_style") or "",
            "text": settings.get("thumbnail_text") or "",
            "url": settings.get("thumbnail_url") or "",
            "path": settings.get("thumbnail_path") or "",
            "idea_count": len(thumbnails.get("ideas") or []) if isinstance(thumbnails, dict) else 0,
            "has_full_settings": bool(thumbnails.get("full_settings")) if isinstance(thumbnails, dict) else False,
        },
        "tts": {
            "voice_name": settings.get("voice_name") or "",
            "voice_language": settings.get("voice_language") or "",
            "voice_provider": settings.get("voice_provider") or "",
            "voice_speed": settings.get("voice_speed") or "",
            "voice_style_prompt": settings.get("voice_style_prompt") or "",
            "voice_mapping": _loads(settings.get("voice_mapping_json"), {}),
        },
        "video": {
            "video_path": settings.get("video_path") or "",
            "intro_video_path": settings.get("intro_video_path") or "",
            "background_video_url": settings.get("background_video_url") or "",
            "duration_seconds": settings.get("duration_seconds") or 0,
            "asset_mix_summary": _loads(settings.get("asset_mix_summary_json"), {}),
            "video_clip_ratio": settings.get("video_clip_ratio") or "",
        },
        "qa": {
            "status": settings.get("qa_status") or "",
            "hold_upload": settings.get("qa_hold_upload") or "0",
            "checked_at": settings.get("qa_checked_at") or "",
            "result": _loads(settings.get("qa_result_json"), {}),
        },
        "upload": {
            "youtube_video_id": settings.get("youtube_video_id") or "",
            "is_uploaded": settings.get("is_uploaded") or 0,
            "is_published": settings.get("is_published") or 0,
            "privacy": settings.get("upload_privacy") or "",
            "schedule_at": settings.get("upload_schedule_at") or "",
            "channel_id": settings.get("youtube_channel_id") or "",
        },
    }


def _sync_remote_best_effort():
    def _run():
        try:
            from services.learning_sync_service import sync_learning_data
            sync_learning_data(limit=50)
        except Exception as exc:
            print(f"[Learning] Remote sync skipped: {exc}")

    threading.Thread(target=_run, daemon=True).start()


def log_event(project_id: int, event_type: str, stage: str = "", payload: Optional[Dict[str, Any]] = None, source: str = "system") -> Optional[int]:
    try:
        event_id = db.log_learning_event(project_id, event_type, stage, payload or {}, source)
        if event_id:
            _sync_remote_best_effort()
        return event_id
    except Exception as exc:
        print(f"[Learning] Event log failed: {exc}")
        return None


def snapshot_project(project_id: int, snapshot_type: str = "manual", extra: Optional[Dict[str, Any]] = None) -> Optional[int]:
    try:
        context = collect_project_learning_context(project_id)
        if extra:
            context.setdefault("upload", {}).update(extra.get("upload", {}))
            context.setdefault("qa", {}).update(extra.get("qa", {}))
            context["extra"] = extra
        snapshot_id = db.create_learning_snapshot(project_id, snapshot_type, context)
        if snapshot_id:
            _sync_remote_best_effort()
        return snapshot_id
    except Exception as exc:
        print(f"[Learning] Snapshot failed: {exc}")
        return None


def _build_event_stats(events: list[Dict[str, Any]]) -> Dict[str, Any]:
    event_counts: Dict[str, int] = {}
    stage_counts: Dict[str, int] = {}
    source_counts: Dict[str, int] = {}
    ratings = []
    latest_manual_review = None

    for event in events or []:
        event_type = event.get("event_type") or "unknown"
        stage = event.get("stage") or "unknown"
        source = event.get("source") or "unknown"
        payload = event.get("payload") or {}

        event_counts[event_type] = event_counts.get(event_type, 0) + 1
        stage_counts[stage] = stage_counts.get(stage, 0) + 1
        source_counts[source] = source_counts.get(source, 0) + 1

        if event_type == "manual_review":
            if latest_manual_review is None:
                latest_manual_review = event
            try:
                rating = payload.get("rating")
                if rating not in (None, ""):
                    ratings.append(float(rating))
            except Exception:
                pass

    return {
        "total_events": len(events or []),
        "event_counts": event_counts,
        "stage_counts": stage_counts,
        "source_counts": source_counts,
        "manual_review_count": event_counts.get("manual_review", 0),
        "upload_completed_count": event_counts.get("upload_completed", 0),
        "upload_failed_count": event_counts.get("upload_failed", 0),
        "qa_hold_count": event_counts.get("qa_hold", 0),
        "reference_selected_count": event_counts.get("reference_selected", 0),
        "thumbnail_edit_count": event_counts.get("human_edit", 0),
        "average_rating": round(sum(ratings) / len(ratings), 2) if ratings else None,
        "latest_manual_review": latest_manual_review,
    }


def get_project_summary(project_id: int) -> Dict[str, Any]:
    context = collect_project_learning_context(project_id)
    all_events = _safe_call(lambda: db.get_learning_events(project_id, 1000), []) or []
    latest_pre_upload = _safe_call(lambda: db.get_learning_snapshot(project_id, "pre_upload"), None)
    latest_post_upload = _safe_call(lambda: db.get_learning_snapshot(project_id, "post_upload"), None)
    latest_manual_review = _safe_call(lambda: db.get_learning_snapshot(project_id, "manual_review"), None)
    return {
        "context": context,
        "stats": _build_event_stats(all_events),
        "recent_events": all_events[:20],
        "latest_pre_upload_snapshot": latest_pre_upload,
        "latest_post_upload_snapshot": latest_post_upload,
        "latest_manual_review_snapshot": latest_manual_review,
    }
