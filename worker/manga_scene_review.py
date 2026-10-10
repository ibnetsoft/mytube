"""Transition rendered manga AE clips through explicit visual review."""
from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _scene_number(scene: dict[str, Any], fallback: int) -> int:
    try:
        return int(scene.get("scene_number") or scene.get("scene_order") or fallback)
    except (TypeError, ValueError):
        return fallback


def apply_review(
    structure: dict[str, Any], *, scene_number: int, decision: str,
    reviewer: str, note: str, expected_sha256: str,
    allowed_media_root: Path,
) -> dict[str, Any]:
    """Mutate a stored scene only after the reviewed MP4 still matches its hash."""
    if decision not in {"approved", "rejected"}:
        raise ValueError("review decision must be approved or rejected")
    if not reviewer.strip() or not note.strip():
        raise ValueError("reviewer and visual-review note are required")
    if len(expected_sha256) != 64 or any(ch not in "0123456789abcdef" for ch in expected_sha256):
        raise ValueError("expected render SHA-256 is invalid")
    scenes = structure.get("scenes")
    if not isinstance(scenes, list):
        raise ValueError("project structure has no scenes")
    scene = next((item for index, item in enumerate(scenes, 1)
                  if isinstance(item, dict) and _scene_number(item, index) == scene_number), None)
    if scene is None:
        raise ValueError("scene was not found")
    plan = scene.get("ae_effect_plan") if isinstance(scene.get("ae_effect_plan"), dict) else {}
    if not plan.get("template"):
        raise ValueError("scene has no manga AE template")
    metadata = scene.get("metadata") if isinstance(scene.get("metadata"), dict) else {}
    asset = metadata.get("ae_effect_asset") if isinstance(metadata.get("ae_effect_asset"), dict) else {}
    if asset.get("status") != "review_pending":
        raise ValueError("scene is not pending visual review")
    if asset.get("render_sha256") != expected_sha256:
        raise ValueError("reviewed render hash changed; refresh the review")
    qa = asset.get("manga_qa") if isinstance(asset.get("manga_qa"), dict) else {}
    if not all(isinstance(qa.get(stage), dict) and qa[stage].get("passed") for stage in ("plan", "render")):
        raise ValueError("scene QA has not passed")
    path_value = str(asset.get("review_local_path") or "")
    path = Path(path_value).resolve() if path_value else None
    root = allowed_media_root.resolve()
    if path is None or not path.is_relative_to(root) or not path.is_file():
        raise ValueError("reviewed local MP4 is unavailable")
    if _file_hash(path) != expected_sha256:
        raise ValueError("reviewed MP4 changed since render")
    status = "ready" if decision == "approved" else "needs_attention"
    asset["status"] = status
    asset["visual_review"] = {
        "decision": decision, "reviewer": reviewer.strip(), "note": note.strip(),
        "render_sha256": expected_sha256,
        "reviewed_at": datetime.now(timezone.utc).isoformat(),
    }
    if decision == "rejected":
        asset["error"] = "Visual review rejected: " + note.strip()[:300]
        scene.pop("ae_video_url", None)
        if asset.get("media_url") and scene.get("video_url") == asset["media_url"]:
            scene.pop("video_url", None)
    elif asset.get("media_url"):
        scene["ae_video_url"] = asset["media_url"]
        scene["video_url"] = asset["media_url"]
    scene["ae_effect_status"] = status
    scene["asset_status"] = status
    return structure
