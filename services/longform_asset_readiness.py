"""Canonical Longform Scene asset readiness evaluation."""

from __future__ import annotations

import datetime
import json
from typing import Any, Dict, Iterable, List

import database as db
from app.modes import normalize_app_mode


READINESS_POLICY = "image_or_video"
TERMINAL_PROJECT_STATUSES = {
    "rendered",
    "completed",
    "published",
    "uploaded",
    "youtube_published",
}


def _has_value(value: Any) -> bool:
    return bool(str(value or "").strip())


def evaluate_scene_asset_readiness(scenes: Iterable[Dict[str, Any]]) -> Dict[str, Any]:
    """Evaluate ordered Scene readiness using the Longform MVP policy."""
    scene_map: Dict[int, Dict[str, Any]] = {}
    duplicate_scene_numbers: List[int] = []

    for scene in scenes or []:
        try:
            scene_number = int(scene.get("scene_number") or 0)
        except (TypeError, ValueError):
            continue
        if scene_number <= 0:
            continue
        if scene_number in scene_map:
            duplicate_scene_numbers.append(scene_number)
            continue
        scene_map[scene_number] = scene

    highest_scene_number = max(scene_map, default=0)
    expected_scene_numbers = list(range(1, highest_scene_number + 1))
    missing_scene_rows = [
        number for number in expected_scene_numbers if number not in scene_map
    ]
    missing_image_scenes = [
        number
        for number in expected_scene_numbers
        if number not in scene_map or not _has_value(scene_map[number].get("image_url"))
    ]
    missing_video_scenes = [
        number
        for number in expected_scene_numbers
        if number not in scene_map or not _has_value(scene_map[number].get("video_url"))
    ]
    missing_asset_scenes = [
        number
        for number in expected_scene_numbers
        if number not in scene_map
        or not (
            _has_value(scene_map[number].get("image_url"))
            or _has_value(scene_map[number].get("video_url"))
        )
    ]
    ready_scene_count = len(expected_scene_numbers) - len(missing_asset_scenes)
    completion_percent = (
        round((ready_scene_count / len(expected_scene_numbers)) * 100)
        if expected_scene_numbers
        else 0
    )
    duplicate_scene_numbers = sorted(set(duplicate_scene_numbers))
    assets_ready = bool(expected_scene_numbers) and not (
        missing_asset_scenes or missing_scene_rows or duplicate_scene_numbers
    )

    return {
        "applicable": True,
        "policy": READINESS_POLICY,
        "assets_ready": assets_ready,
        "completion_percent": completion_percent,
        "total_scenes": len(expected_scene_numbers),
        "ready_scene_count": ready_scene_count,
        "scene_order": expected_scene_numbers,
        "missing_asset_scenes": missing_asset_scenes,
        "missing_image_scenes": missing_image_scenes,
        "missing_video_scenes": missing_video_scenes,
        "missing_scene_rows": missing_scene_rows,
        "duplicate_scene_numbers": duplicate_scene_numbers,
    }


def sync_project_asset_readiness(
    project_id: int,
    *,
    persist: bool = True,
) -> Dict[str, Any]:
    """Evaluate a Longform project and optionally persist its canonical state."""
    project = db.get_project(project_id)
    if not project:
        return {
            "applicable": False,
            "reason": "project_not_found",
            "assets_ready": False,
            "project_complete": False,
        }

    settings = db.get_project_settings(project_id) or {}
    app_mode = normalize_app_mode(
        settings.get("app_mode") or project.get("app_mode") or "longform"
    )
    if app_mode != "longform":
        return {
            "applicable": False,
            "reason": "not_longform",
            "app_mode": app_mode,
            "assets_ready": False,
            "project_complete": False,
        }

    result = evaluate_scene_asset_readiness(db.get_image_prompts(project_id))
    project_status = str(project.get("status") or "").strip().lower()
    result.update(
        {
            "project_id": project_id,
            "app_mode": app_mode,
            "project_status": project_status,
            "project_complete": bool(
                result["assets_ready"]
                and project_status in TERMINAL_PROJECT_STATUSES
            ),
        }
    )

    if persist:
        readiness_json = json.dumps(result, ensure_ascii=False, sort_keys=True)
        ready_at = (
            settings.get("assets_ready_at")
            if result["assets_ready"] and settings.get("assets_ready_at")
            else (
                datetime.datetime.now(datetime.timezone.utc).isoformat()
                if result["assets_ready"]
                else ""
            )
        )
        desired = {
            "assets_ready": 1 if result["assets_ready"] else 0,
            "asset_completion_percent": result["completion_percent"],
            "asset_readiness_json": readiness_json,
            "assets_ready_at": ready_at,
            "project_complete": 1 if result["project_complete"] else 0,
        }
        for key, value in desired.items():
            if key in {
                "assets_ready",
                "asset_completion_percent",
                "project_complete",
            }:
                unchanged = int(settings.get(key) or 0) == int(value)
            else:
                unchanged = str(settings.get(key) or "") == str(value)
            if not unchanged:
                db.update_project_setting(project_id, key, value)

    return result
