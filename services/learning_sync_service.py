"""Best-effort Supabase sync for project learning events and snapshots."""

from __future__ import annotations

import datetime
from typing import Any, Dict

import database as db
from services.web_admin_client import web_admin_client


LEARNING_EVENTS_TABLE = "project_learning_events"
LEARNING_SNAPSHOTS_TABLE = "project_learning_snapshots"


def _utc_now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def _resolve_user_id(email: str) -> str:
    if not email:
        return ""
    try:
        return web_admin_client.resolve_user_id(email=email) or ""
    except Exception:
        return ""


def _event_payload(row: Dict[str, Any]) -> Dict[str, Any]:
    email = row.get("employee_email") or ""
    project_sync_id = row.get("project_sync_id") or "local"
    local_event_id = row.get("id")
    return {
        "sync_key": f"event:{project_sync_id}:{local_event_id}",
        "local_event_id": local_event_id,
        "local_project_id": row.get("project_id"),
        "project_sync_id": row.get("project_sync_id"),
        "user_id": _resolve_user_id(email) or None,
        "employee_email": email or None,
        "project_name": row.get("project_name") or "",
        "project_topic": row.get("project_topic") or "",
        "event_type": row.get("event_type") or "",
        "stage": row.get("stage") or "",
        "source": row.get("source") or "system",
        "payload": row.get("payload") or {},
        "local_created_at": row.get("created_at"),
        "synced_at": _utc_now(),
    }


def _snapshot_payload(row: Dict[str, Any]) -> Dict[str, Any]:
    email = row.get("employee_email") or ""
    project_sync_id = row.get("project_sync_id") or "local"
    local_snapshot_id = row.get("id")
    return {
        "sync_key": f"snapshot:{project_sync_id}:{local_snapshot_id}",
        "local_snapshot_id": local_snapshot_id,
        "local_project_id": row.get("project_id"),
        "project_sync_id": row.get("project_sync_id"),
        "user_id": _resolve_user_id(email) or None,
        "employee_email": email or None,
        "project_name": row.get("project_name") or "",
        "project_topic": row.get("project_topic") or "",
        "snapshot_type": row.get("snapshot_type") or "manual",
        "reference": row.get("reference") or {},
        "style": row.get("style") or {},
        "script": row.get("script") or {},
        "thumbnail": row.get("thumbnail") or {},
        "tts": row.get("tts") or {},
        "video": row.get("video") or {},
        "qa": row.get("qa") or {},
        "upload": row.get("upload") or {},
        "local_created_at": row.get("created_at"),
        "synced_at": _utc_now(),
    }


def _upsert_learning_row(table: str, key: str, payload: Dict[str, Any]) -> bool:
    if not web_admin_client.has_supabase():
        return False
    return web_admin_client.upsert_by_key(table, key, payload[key], payload, timeout=10)


def sync_learning_data(limit: int = 100) -> Dict[str, int]:
    """Sync pending learning events/snapshots to Supabase without blocking production flows."""
    result = {
        "events_attempted": 0,
        "events_synced": 0,
        "events_failed": 0,
        "snapshots_attempted": 0,
        "snapshots_synced": 0,
        "snapshots_failed": 0,
    }

    if not web_admin_client.has_supabase():
        return result

    for event in db.get_unsynced_learning_events(limit):
        event_id = event.get("id")
        result["events_attempted"] += 1
        try:
            payload = _event_payload(event)
            if _upsert_learning_row(LEARNING_EVENTS_TABLE, "sync_key", payload):
                db.mark_learning_event_remote_synced(event_id, payload["synced_at"])
                result["events_synced"] += 1
            else:
                db.mark_learning_event_remote_sync_error(event_id, "Supabase upsert returned false")
                result["events_failed"] += 1
        except Exception as exc:
            db.mark_learning_event_remote_sync_error(event_id, str(exc))
            result["events_failed"] += 1

    for snapshot in db.get_unsynced_learning_snapshots(limit):
        snapshot_id = snapshot.get("id")
        result["snapshots_attempted"] += 1
        try:
            payload = _snapshot_payload(snapshot)
            if _upsert_learning_row(LEARNING_SNAPSHOTS_TABLE, "sync_key", payload):
                db.mark_learning_snapshot_remote_synced(snapshot_id, payload["synced_at"])
                result["snapshots_synced"] += 1
            else:
                db.mark_learning_snapshot_remote_sync_error(snapshot_id, "Supabase upsert returned false")
                result["snapshots_failed"] += 1
        except Exception as exc:
            db.mark_learning_snapshot_remote_sync_error(snapshot_id, str(exc))
            result["snapshots_failed"] += 1

    if result["events_attempted"] or result["snapshots_attempted"]:
        print(f"[LearningSync] {result}")
    return result
