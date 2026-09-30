"""After Effects highlight renderer for prepared topic scene images.

This worker polls topics_queue for scenes with ae_effect_plan.enabled=true,
downloads the scene image from GCS, renders a short AE CS6-compatible effect
clip, uploads the MP4 back to GCS, and writes the result to
pregenerated_structure.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import mimetypes
import os
import re
import shutil
import subprocess
import sys
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, quote, urlparse

import requests

import worker_config
from adobe_tools import find_aerender, find_afterfx
from ae_recovery import AeRecoveryError, continue_crash_recovery
from manga_ae_templates import template_for_scene, write_manga_jsx
from manga_scene_qa import validate_scene_plan, validate_render
from media_checkpoint import Checkpoint, fingerprint, valid_file, valid_mp4, verified_local_mp4
from shutdown_flag import clear_shutdown_flag, is_shutdown_requested


ROOT = Path(__file__).resolve().parent.parent
STATE_DIR = worker_config.STATE_DIR / "ae_highlight"
STATE_DIR.mkdir(parents=True, exist_ok=True)
WORKER_STATE_FILE = worker_config.STATE_DIR / "ae_highlight_worker.json"

DEFAULT_AFTERFX = r"C:\Program Files\Adobe\Adobe After Effects CS6\Support Files\AfterFX.com"
FALLBACK_AFTERFX_EXE = r"C:\Program Files\Adobe\Adobe After Effects CS6\Support Files\AfterFX.exe"
DEFAULT_AERENDER = r"C:\Program Files\Adobe\Adobe After Effects CS6\Support Files\aerender.exe"
DEFAULT_BUCKET = os.getenv("GCS_BUCKET_NAME") or "air-studio-prod"
DEFAULT_WIDTH = int(os.getenv("AE_HIGHLIGHT_WIDTH", "1920"))
DEFAULT_HEIGHT = int(os.getenv("AE_HIGHLIGHT_HEIGHT", "1080"))
DEFAULT_FPS = int(os.getenv("AE_HIGHLIGHT_FPS", "24"))
DEFAULT_POLL_SECONDS = float(os.getenv("AE_HIGHLIGHT_POLL_SECONDS", "20"))
DEFAULT_TOPIC_LIMIT = int(os.getenv("AE_HIGHLIGHT_TOPIC_LIMIT", "20"))
DEFAULT_MAX_SCENES_PER_TICK = int(os.getenv("AE_HIGHLIGHT_MAX_SCENES_PER_TICK", "3"))
MAX_ATTEMPTS = int(os.getenv("AE_HIGHLIGHT_MAX_ATTEMPTS", "3"))


class AeWorkerError(RuntimeError):
    pass


class AeSceneConflict(AeWorkerError):
    """The database scene changed after this worker read it."""
    pass


class AeReviewRequired(AeWorkerError):
    """A deterministic input or QA failure that needs asset/plan correction."""
    pass


@dataclass(frozen=True)
class GcsRef:
    bucket: str
    path: str


@dataclass(frozen=True)
class SceneJob:
    topic_id: str
    topic_title: str
    structure: dict[str, Any]
    scene_index: int
    scene: dict[str, Any]
    scene_number: int
    plan_kind: str
    preset: str
    duration_seconds: float
    source: GcsRef
    source_type: str = "topic"
    project_payload: dict[str, Any] | None = None


def write_state(
    status: str,
    progress: int = 0,
    current_job: dict[str, Any] | None = None,
    last_error: str | None = None,
) -> None:
    previous = {}
    if WORKER_STATE_FILE.exists():
        try:
            previous = json.loads(WORKER_STATE_FILE.read_text(encoding="utf-8"))
        except Exception:
            previous = {}
    WORKER_STATE_FILE.write_text(
        json.dumps(
            {
                "pid": os.getpid(),
                "status": status,
                "current_job": current_job,
                "current_job_id": (current_job or {}).get("job_id"),
                "progress": progress,
                "worker_instance_id": worker_config.WORKER_INSTANCE_ID,
                "heartbeat_at": time.time(),
                "last_success_at": previous.get("last_success_at"),
                "last_error": previous.get("last_error") if last_error is None else last_error,
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _safe_name(value: Any, fallback: str = "item") -> str:
    text = str(value or "").strip().lower()
    text = re.sub(r"[^a-z0-9._-]+", "-", text)
    text = re.sub(r"-{2,}", "-", text).strip("-._")
    return text[:80] or fallback


def _json_object(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str) and value.strip():
        parsed = json.loads(value)
        if isinstance(parsed, dict):
            return parsed
    return {}


def _supabase() -> tuple[str, dict[str, str]]:
    url = (os.getenv("NEXT_PUBLIC_SUPABASE_URL") or os.getenv("SUPABASE_URL") or "").rstrip("/")
    key = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or ""
    if not url or not key:
        raise AeWorkerError("NEXT_PUBLIC_SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY are required")
    return url, {"apikey": key, "Authorization": f"Bearer {key}"}


def _request(method: str, url: str, headers: dict[str, str], **kwargs: Any) -> requests.Response:
    response = requests.request(method, url, headers=headers, timeout=60, **kwargs)
    if not response.ok:
        raise AeWorkerError(f"Supabase request failed ({response.status_code}): {response.text[:500]}")
    return response


def _gcs_credentials():
    client_email = os.getenv("GCS_CLIENT_EMAIL") or os.getenv("GOOGLE_CLIENT_EMAIL") or ""
    private_key = os.getenv("GCS_PRIVATE_KEY") or os.getenv("GOOGLE_PRIVATE_KEY") or ""
    project_id = os.getenv("GCS_PROJECT_ID") or os.getenv("GOOGLE_CLOUD_PROJECT") or "air-studio-prod"
    bucket = os.getenv("GCS_BUCKET_NAME") or DEFAULT_BUCKET
    if not (client_email and private_key and bucket):
        raise AeWorkerError("GCS credentials are required for AE highlight rendering")
    from google.oauth2 import service_account
    from google.auth.transport.requests import Request

    creds = service_account.Credentials.from_service_account_info(
        {
            "type": "service_account",
            "project_id": project_id,
            "private_key": private_key.replace("\\n", "\n"),
            "client_email": client_email,
            "token_uri": "https://oauth2.googleapis.com/token",
        },
        scopes=["https://www.googleapis.com/auth/devstorage.read_write"],
    )
    creds.refresh(Request())
    return creds, bucket


def _download_gcs_file(ref: GcsRef, target: Path) -> None:
    if ref.bucket == "__local__":
        source = Path(ref.path).expanduser().resolve()
        if not source.is_file():
            raise AeWorkerError(f"Local AE source image is missing: {source}")
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        return
    creds, default_bucket = _gcs_credentials()
    bucket = ref.bucket or default_bucket
    clean_path = ref.path.strip().replace("\\", "/").lstrip("/")
    if not clean_path:
        raise AeWorkerError("GCS object path is empty")
    response = requests.get(
        f"https://storage.googleapis.com/storage/v1/b/{quote(bucket, safe='')}/o/"
        f"{quote(clean_path, safe='')}?alt=media",
        headers={"Authorization": f"Bearer {creds.token}"},
        timeout=300,
    )
    if response.status_code != 200:
        raise AeWorkerError(f"GCS download failed ({response.status_code}): {response.text[:300]}")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(response.content)


def _upload_gcs_file(file_path: Path, object_path: str, mime_type: str) -> tuple[str, str, str]:
    creds, bucket = _gcs_credentials()
    clean_path = str(object_path or "").strip().replace("\\", "/").lstrip("/")
    if not clean_path:
        raise AeWorkerError("GCS object path is empty")
    with file_path.open("rb") as handle:
        response = requests.post(
            f"https://storage.googleapis.com/upload/storage/v1/b/{quote(bucket, safe='')}/o"
            f"?uploadType=media&name={quote(clean_path, safe='')}",
            headers={"Authorization": f"Bearer {creds.token}", "Content-Type": mime_type},
            data=handle,
            timeout=600,
        )
    if response.status_code not in (200, 201):
        raise AeWorkerError(f"GCS upload failed ({response.status_code}): {response.text[:300]}")
    return bucket, clean_path, f"/api/std/assets/gcs-file?bucket={quote(bucket, safe='')}&path={quote(clean_path, safe='')}"


def _gcs_ref_from_scene(scene: dict[str, Any]) -> GcsRef | None:
    metadata = scene.get("metadata") if isinstance(scene.get("metadata"), dict) else {}
    motion_plan = scene.get("ae_motion_plan") if isinstance(scene.get("ae_motion_plan"), dict) else {}
    source_kind = str(motion_plan.get("input_source") or "").strip().lower()
    video_mode = str(scene.get("video_generation_mode") or metadata.get("video_generation_mode") or "").strip().lower()
    # When a post-process plan names generated video as its input, never fall
    # back to the scene's still image. Wait for the registered clip instead.
    if source_kind in {"comfyui_video_asset", "uploaded_video_asset"} or video_mode in {"comfyui", "user_upload"}:
        asset_key = "comfyui_video_asset" if source_kind == "comfyui_video_asset" or video_mode == "comfyui" else "video_asset"
        asset = metadata.get(asset_key) if isinstance(metadata.get(asset_key), dict) else {}
        if not asset and asset_key == "video_asset":
            asset = metadata.get("cowork_video_asset") if isinstance(metadata.get("cowork_video_asset"), dict) else {}
        path = str(asset.get("gcs_path") or asset.get("object_path") or asset.get("storage_path")
                   or metadata.get("video_gcs_path") or metadata.get("uploaded_video_path") or "").strip()
        if not path and asset.get("storage_url"):
            path = str(asset.get("storage_url") or "").strip()
        if not path.lower().endswith((".mp4", ".mov", ".webm", ".m4v")):
            return None
        return GcsRef(bucket=str(asset.get("gcs_bucket") or asset.get("bucket") or asset.get("storage_bucket")
                                  or metadata.get("video_gcs_bucket") or metadata.get("uploaded_video_bucket") or DEFAULT_BUCKET), path=path)
    layered = metadata.get("psd_layer_asset") if isinstance(metadata.get("psd_layer_asset"), dict) else {}
    layered_path = str(layered.get("gcs_path") or layered.get("object_path") or "").strip()
    if layered_path.lower().endswith(".psd"):
        return GcsRef(bucket=str(layered.get("gcs_bucket") or layered.get("bucket") or DEFAULT_BUCKET), path=layered_path)
    # For explicitly planned post-effects, uploaded/ComfyUI clips can be the
    # source footage. Otherwise preserve the existing PSD/still-image path.
    video_asset = metadata.get("video_asset") if isinstance(metadata.get("video_asset"), dict) else {}
    comfy_asset = metadata.get("comfyui_video_asset") if isinstance(metadata.get("comfyui_video_asset"), dict) else {}
    video_path = str(
        comfy_asset.get("gcs_path") or comfy_asset.get("object_path")
        or video_asset.get("gcs_path") or video_asset.get("object_path")
        or metadata.get("video_gcs_path") or metadata.get("video_storage_path") or ""
    ).strip()
    if video_path.lower().endswith((".mp4", ".mov", ".webm", ".m4v")):
        return GcsRef(bucket=str(
            comfy_asset.get("gcs_bucket") or comfy_asset.get("bucket")
            or video_asset.get("gcs_bucket") or video_asset.get("bucket")
            or metadata.get("video_gcs_bucket") or metadata.get("video_storage_bucket") or DEFAULT_BUCKET
        ), path=video_path)
    asset = metadata.get("cowork_image_asset") if isinstance(metadata.get("cowork_image_asset"), dict) else {}
    local_path = str(asset.get("local_path") or "").strip()
    if asset.get("storage_provider") == "local" and local_path:
        return GcsRef(bucket="__local__", path=local_path)
    # Locally prepared AE motion plans may point directly at the cropped still
    # in the user's workspace. This avoids uploading a still to GCS only to
    # download it again on the same machine for rendering.
    planned_local_path = str(motion_plan.get("local_source_path") or "").strip()
    if planned_local_path:
        return GcsRef(bucket="__local__", path=planned_local_path)
    bucket = str(
        asset.get("gcs_bucket")
        or asset.get("bucket")
        or metadata.get("gcs_bucket")
        or metadata.get("storage_bucket")
        or ""
    ).strip()
    path = str(
        asset.get("gcs_path")
        or asset.get("object_path")
        or metadata.get("gcs_path")
        or metadata.get("storage_path")
        or ""
    ).strip()
    if path:
        return GcsRef(bucket=bucket or DEFAULT_BUCKET, path=path)

    image_url = str(scene.get("image_url") or "").strip()
    if image_url.startswith("/api/std/assets/gcs-file?"):
        query = parse_qs(urlparse(image_url).query)
        url_bucket = (query.get("bucket") or [""])[0]
        url_path = (query.get("path") or [""])[0]
        if url_path:
            return GcsRef(bucket=url_bucket or DEFAULT_BUCKET, path=url_path)
    return None


def _scene_requires_comfyui(scene: dict[str, Any]) -> bool:
    """Only queue AE post-processing for ComfyUI scenes after their clip exists."""
    metadata = scene.get("metadata") if isinstance(scene.get("metadata"), dict) else {}
    generation_mode = str(scene.get("video_generation_mode") or metadata.get("video_generation_mode") or "").lower()
    if generation_mode != "comfyui":
        return False
    asset = metadata.get("comfyui_video_asset") if isinstance(metadata.get("comfyui_video_asset"), dict) else {}
    path = str(
        asset.get("gcs_path") or asset.get("object_path")
        or metadata.get("video_gcs_path") or metadata.get("video_storage_path") or ""
    ).strip()
    return bool(path and path.lower().endswith((".mp4", ".mov", ".webm", ".m4v")))


def _scene_requires_uploaded_video(scene: dict[str, Any]) -> bool:
    """Only queue user-upload post-processing once their video is registered."""
    metadata = scene.get("metadata") if isinstance(scene.get("metadata"), dict) else {}
    mode = str(scene.get("video_generation_mode") or metadata.get("video_generation_mode") or "").lower()
    if mode != "user_upload":
        return False
    candidates = [metadata.get("video_asset"), metadata.get("cowork_video_asset")]
    for value in candidates:
        asset = value if isinstance(value, dict) else {}
        path = str(asset.get("gcs_path") or asset.get("object_path") or asset.get("storage_path") or "").strip()
        if path.lower().endswith((".mp4", ".mov", ".webm", ".m4v")):
            return True
    return any(
        str(scene.get(key) or "").strip().lower().endswith((".mp4", ".mov", ".webm", ".m4v"))
        for key in ("video_url", "uploaded_video_url")
    )


def _render_plan_from_scene(scene: dict[str, Any]) -> tuple[str, dict[str, Any]] | None:
    effect_plan = scene.get("ae_effect_plan") if isinstance(scene.get("ae_effect_plan"), dict) else {}
    if effect_plan.get("enabled"):
        return "effect", effect_plan
    motion_plan = scene.get("ae_motion_plan") if isinstance(scene.get("ae_motion_plan"), dict) else {}
    if motion_plan.get("enabled"):
        return "motion", motion_plan
    return None


def _asset_key(job_or_kind: SceneJob | str) -> str:
    kind = job_or_kind.plan_kind if isinstance(job_or_kind, SceneJob) else str(job_or_kind)
    return "ae_motion_asset" if kind == "motion" else "ae_effect_asset"


def _status_key(job_or_kind: SceneJob | str) -> str:
    kind = job_or_kind.plan_kind if isinstance(job_or_kind, SceneJob) else str(job_or_kind)
    return "ae_motion_status" if kind == "motion" else "ae_effect_status"


def _video_url_key(job_or_kind: SceneJob | str) -> str:
    kind = job_or_kind.plan_kind if isinstance(job_or_kind, SceneJob) else str(job_or_kind)
    return "ae_motion_video_url" if kind == "motion" else "ae_video_url"


def _scene_delivery(source_type: str, project_payload: dict[str, Any] | None,
                    structure: dict[str, Any], scene: dict[str, Any]) -> str:
    """Use a topic's explicit delivery choice before the host-wide fallback."""
    payload = project_payload or {}
    settings = payload.get("render_settings") if isinstance(payload.get("render_settings"), dict) else {}
    brief = payload.get("web_brief") if isinstance(payload.get("web_brief"), dict) else {}
    source = payload.get("source_payload") if isinstance(payload.get("source_payload"), dict) else {}
    candidates = (payload.get("ae_scene_delivery"), settings.get("ae_scene_delivery"),
                  brief.get("ae_scene_delivery"), source.get("ae_scene_delivery"),
                  structure.get("ae_scene_delivery"), scene.get("ae_scene_delivery"),
                  os.getenv("AE_SCENE_DELIVERY"))
    for candidate in candidates:
        if candidate is None or candidate == "":
            continue
        value = str(candidate).strip().lower()
        if value not in {"local", "gcs"}:
            raise AeWorkerError(f"Unknown ae_scene_delivery: {value}")
        return value
    return "local" if source_type == "project" else "gcs"


def _find_scene_jobs(rows: list[dict[str, Any]], force: bool = False) -> list[SceneJob]:
    jobs: list[SceneJob] = []
    for row in rows:
        topic_id = str(row.get("id") or "")
        source_type = str(row.get("__source_type") or "topic")
        project_payload = _json_object(row.get("project_payload")) if source_type == "project" else None
        structure = _json_object(project_payload.get("structure")) if project_payload is not None else _json_object(row.get("pregenerated_structure"))
        scenes = structure.get("scenes")
        if not topic_id or not isinstance(scenes, list):
            continue
        for index, scene in enumerate(scenes):
            if not isinstance(scene, dict):
                continue
            render_plan = _render_plan_from_scene(scene)
            if not render_plan:
                continue
            # ComfyUI scenes have an AE post-process plan before generation,
            # but must not be claimed until the source clip has been registered.
            video_mode = str(scene.get("video_generation_mode") or "").lower()
            if video_mode == "comfyui" and not _scene_requires_comfyui(scene):
                continue
            if video_mode == "user_upload" and not _scene_requires_uploaded_video(scene):
                continue
            plan_kind, plan = render_plan
            meta = scene.get("metadata") if isinstance(scene.get("metadata"), dict) else {}
            asset_key = _asset_key(plan_kind)
            url_key = _video_url_key(plan_kind)
            ae_meta = meta.get(asset_key) if isinstance(meta.get(asset_key), dict) else {}
            delivery = _scene_delivery(source_type, project_payload, structure, scene)
            if not force:
                if delivery == "local" and ae_meta.get("storage_provider") == "local" and ae_meta.get("status") == "ready":
                    try:
                        required_seconds = max(0.5, float(ae_meta.get("duration_seconds") or 1) * 0.8)
                    except (TypeError, ValueError):
                        required_seconds = 0.5
                    if verified_local_mp4(ae_meta.get("local_path"), worker_config.TEMP_DIR / "ae_highlight",
                                          required_seconds):
                        continue
                elif (delivery == "gcs" and ae_meta.get("storage_provider") != "local" and
                      (ae_meta.get("status") == "ready" or
                       (scene.get(url_key) and ae_meta.get("status") in {None, "", "ready"}))):
                    continue
            if not force and ae_meta.get("status") in {"needs_attention", "review_pending"}:
                continue
            if not force and float(ae_meta.get("next_retry_at") or 0) > time.time():
                continue
            if plan_kind == "effect" and plan.get("template"):
                layered = meta.get("psd_layer_asset") if isinstance(meta.get("psd_layer_asset"), dict) else {}
                layered_path = str(layered.get("gcs_path") or layered.get("object_path") or "").strip()
                # Claim-time projects can exist before their separate PSD
                # package is approved. Never consume a flattened preview and
                # leave a permanent missing-PSD failure while it is arriving.
                if layered.get("qa_status") != "approved" or not layered_path.lower().endswith(".psd"):
                    continue
            source = _gcs_ref_from_scene(scene)
            if not source:
                continue
            try:
                scene_number = int(scene.get("scene_number") or scene.get("scene_order") or (index + 1))
            except (TypeError, ValueError):
                scene_number = index + 1
            try:
                duration = float(plan.get("duration_seconds") or scene.get("duration_seconds") or 4)
            except (TypeError, ValueError):
                duration = 4.0
            jobs.append(
                SceneJob(
                    topic_id=topic_id,
                    topic_title=str(row.get("title") or row.get("generated_title") or row.get("topic") or topic_id),
                    structure=structure,
                    scene_index=index,
                    scene=scene,
                    scene_number=scene_number,
                    plan_kind=plan_kind,
                    preset=_safe_name(plan.get("preset"), "wuxia_sword_aura"),
                    duration_seconds=max(1.0, min(duration, 12.0)),
                    source=source,
                    source_type=source_type,
                    project_payload=project_payload,
                )
            )
    jobs.sort(key=lambda job: (0 if job.plan_kind == "effect" else 1, -int((_render_plan_from_scene(job.scene) or ("", {}))[1].get("priority") or 0), job.topic_id, job.scene_number))
    return jobs


def fetch_candidate_topics(limit: int) -> list[dict[str, Any]]:
    base_url, headers = _supabase()
    response = _request(
        "GET",
        f"{base_url}/rest/v1/topics_queue",
        headers,
        params={
            "select": "id,topic,generated_title,pregenerated_structure,pregenerated_structure_status,created_at",
            "pregenerated_structure_status": "eq.ready",
            "order": "created_at.desc",
            "limit": str(limit),
        },
    )
    rows = response.json()
    return rows if isinstance(rows, list) else []


def fetch_candidate_projects(limit: int) -> list[dict[str, Any]]:
    base_url, headers = _supabase()
    response = _request(
        "GET", f"{base_url}/rest/v1/std_projects", headers,
        params={"select": "id,title,submitted_at,project_payload,updated_at",
                "submitted_at": "not.is.null", "order": "updated_at.desc", "limit": str(limit)},
    )
    rows = response.json()
    return [{**row, "__source_type": "project"} for row in rows if isinstance(row, dict)] if isinstance(rows, list) else []


def _patch_job_structure(job: SceneJob, *, expected_status: str = "",
                         expected_started_at: str | None = None,
                         asset_patch: dict[str, Any] | None = None,
                         next_status: str = "", media_url: str | None = None,
                         clear_media_url: bool = False) -> None:
    base_url, headers = _supabase()
    response = _request(
        "POST", f"{base_url}/rest/v1/rpc/air_update_ae_scene",
        {**headers, "Content-Type": "application/json"},
        json={
            "p_source_type": job.source_type, "p_identity": job.topic_id,
            "p_scene_number": job.scene_number, "p_operation": "worker",
            "p_plan_kind": job.plan_kind,
            "p_expected_status": expected_status,
            "p_expected_started_at": expected_started_at,
            "p_asset_patch": asset_patch or {}, "p_next_status": next_status,
            "p_media_url": media_url, "p_clear_media_url": clear_media_url,
        },
    )
    result = response.json()
    if not isinstance(result, dict) or not result.get("applied"):
        code = result.get("code") if isinstance(result, dict) else "invalid_response"
        raise AeSceneConflict(f"AE scene update was not applied: {code}")
    updated = result.get("scene")
    if not isinstance(updated, dict):
        raise AeWorkerError("AE scene update returned no scene")
    current = job.structure["scenes"][job.scene_index]
    current.clear()
    current.update(updated)


def _mark_scene(job: SceneJob, status: str, **extra: Any) -> None:
    scene = job.structure["scenes"][job.scene_index]
    metadata = scene.setdefault("metadata", {})
    asset_key = _asset_key(job)
    old_asset = metadata.get(asset_key) if isinstance(metadata.get(asset_key), dict) else {}
    patch = {
        "status": status,
        "plan_kind": job.plan_kind,
        "worker": os.getenv("AE_HIGHLIGHT_WORKER_ID") or worker_config.WORKER_INSTANCE_ID,
        "updated_at": _now(),
        **extra,
    }
    metadata[asset_key] = {**old_asset, **patch}
    scene[_status_key(job)] = status
    _patch_job_structure(job, expected_status=str(old_asset.get("status") or ""),
                         asset_patch=patch, next_status=status,
                         clear_media_url=bool(job.plan_kind == "effect" and
                                              isinstance(job.scene.get("ae_effect_plan"), dict) and
                                              job.scene["ae_effect_plan"].get("template")))


def _job_summary(job: SceneJob) -> dict[str, Any]:
    return {
        "job_id": f"ae:{job.plan_kind}:{job.topic_id}:{job.scene_number}",
        "job_type": "render_ae_highlight" if job.plan_kind == "effect" else "render_ae_motion",
        "source": "std_projects" if job.source_type == "project" else "topics_queue",
        "status": "rendering",
        "project_name": job.topic_title,
        "scene_number": job.scene_number,
        "plan_kind": job.plan_kind,
        "preset": job.preset,
        "progress_message": f"AE {job.plan_kind} scene {job.scene_number} ({job.preset})",
    }


def _ae_path(value: Path) -> str:
    return str(value.resolve()).replace("\\", "/")


def _uploaded_video_review_frames(job: SceneJob, clip_path: Path) -> tuple[list[str], list[float]]:
    """Extract a small set of review frames from the actual uploaded clip."""
    digest = hashlib.sha256()
    with clip_path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    source_sha256 = digest.hexdigest()
    review_dir = ROOT / "output" / "codex-local-console" / "ae-video-review" / f"{_safe_name(job.topic_id)}-{job.scene_number:03d}-{source_sha256[:12]}"
    review_dir.mkdir(parents=True, exist_ok=True)
    ffmpeg = _ffmpeg_executable()
    timestamps = [round(job.duration_seconds * ratio, 3) for ratio in (0.08, 0.5, 0.9)]
    frame_paths: list[str] = []
    used_timestamps: list[float] = []
    for index, timestamp in enumerate(timestamps, 1):
        frame = review_dir / f"frame_{index:02d}_{timestamp:.3f}s.jpg"
        if not frame.is_file() or frame.stat().st_size < 1024:
            result = subprocess.run(
                [ffmpeg, "-y", "-ss", f"{timestamp:.3f}", "-i", str(clip_path),
                 "-frames:v", "1", "-vf", "scale=1024:-2", "-q:v", "3", str(frame)],
                capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=90,
            )
            if result.returncode != 0 or not frame.is_file() or frame.stat().st_size < 1024:
                frame.unlink(missing_ok=True)
                continue
        frame_paths.append(str(frame.resolve()))
        used_timestamps.append(timestamp)
    if len(frame_paths) < 2:
        raise AeReviewRequired("Could not extract at least two representative frames from the uploaded video")
    return frame_paths, used_timestamps


def _review_uploaded_video_direction(job: SceneJob, clip_path: Path) -> tuple[dict[str, Any], str]:
    """Finalize the scene direction against frames sampled from its uploaded clip."""
    frame_paths, timestamps = _uploaded_video_review_frames(job, clip_path)
    digest = hashlib.sha256()
    with clip_path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    source_sha256 = digest.hexdigest()
    asset_key = _asset_key(job)
    metadata = job.scene.get("metadata") if isinstance(job.scene.get("metadata"), dict) else {}
    old_asset = metadata.get(asset_key) if isinstance(metadata.get(asset_key), dict) else {}
    saved_direction = old_asset.get("directorial_plan") if isinstance(old_asset.get("directorial_plan"), dict) else {}
    if saved_direction.get("source_video_sha256") == source_sha256 and saved_direction.get("source_video_review_status") == "reviewed":
        direction = saved_direction
    else:
        from codex_content_runner import CodexStagedContentRunner
        from scene_visual_director import PERSONA, validate_directorial_plans

        scene_context = {
            key: job.scene.get(key)
            for key in ("scene_number", "scene_order", "scene_summary", "scene_situation", "scene_purpose",
                        "scene_emotion", "scene_text", "narration", "dialogue_annotations", "video_prompt",
                        "ae_directorial_plan")
            if job.scene.get(key) is not None
        }
        scene_context["duration_seconds"] = job.duration_seconds
        scene_context["source_video_review"] = {
            "status": "uploaded_clip_keyframes_attached",
            "frame_timestamps_seconds": timestamps,
            "source_sha256": source_sha256,
        }
        result = CodexStagedContentRunner()._stage(
            f"ae-video-{_safe_name(job.topic_id)}-{job.scene_number:03d}-{source_sha256[:12]}",
            "02g_uploaded_video_scene_director",
            {"scenes": [scene_context], "_local_image_paths": frame_paths},
            PERSONA + "\n\nReview the attached frames from this exact uploaded clip in timestamp order. "
            "Return one final scene_directions item with source_video_reviewed=true. "
            "Use no storyboard frames. Keep timed beats tied to visible moments in the attached footage. "
            "Return {'scene_directions':[...]} only.",
        )
        normalized = validate_directorial_plans([scene_context], result)
        direction = {**normalized[0], "source_video_sha256": source_sha256,
                     "review_frame_timestamps_seconds": timestamps}
        if direction.get("source_video_review_status") != "reviewed":
            raise AeReviewRequired("Scene director did not confirm review of the uploaded video frames")

    if direction.get("requires_layered_assets"):
        existing_layers = metadata.get("ae_layer_assets") if isinstance(metadata.get("ae_layer_assets"), list) else []
        available = {str(item.get("role") or "") for item in existing_layers if isinstance(item, dict) and item.get("status") == "ready"}
        requested_roles = set(direction.get("required_layers") or [])
        requested_roles.update(str(item.get("role") or "") for item in direction.get("additional_keyframes", [])
                               if isinstance(item, dict))
        missing = sorted(requested_roles - available)
        if missing:
            raise AeReviewRequired("Scene direction needs prepared layers before AE: " + ", ".join(missing))

    job.scene["ae_directorial_plan"] = direction
    plan_key = "ae_motion_plan" if job.plan_kind == "motion" else "ae_effect_plan"
    render_plan = job.scene.get(plan_key) if isinstance(job.scene.get(plan_key), dict) else {}
    operations = set(direction.get("ae_operations") or [])
    vfx = []
    if "light_flicker" in operations:
        vfx.append("warm_lantern_flicker")
    if "atmosphere_drift" in operations:
        vfx.append("atmospheric_haze")
    render_plan = {**render_plan, "directorial_plan": direction,
                   "direction": direction.get("visual_strategy") or render_plan.get("direction"),
                   "vfx": vfx}
    if "camera_move" not in operations:
        render_plan["motion"] = {"push": 0.0, "drift_x": 0.0, "drift_y": 0.0, "shake": 0.0}
    job.scene[plan_key] = render_plan
    return direction, source_sha256


def _qa_uploaded_video_render(job: SceneJob, render_path: Path,
                             direction: dict[str, Any]) -> dict[str, Any]:
    """Compare representative rendered frames with the approved scene direction."""
    frame_paths, timestamps = _uploaded_video_review_frames(job, render_path)
    from codex_content_runner import CodexStagedContentRunner

    result = CodexStagedContentRunner()._stage(
        f"ae-qa-{_safe_name(job.topic_id)}-{job.scene_number:03d}-{_sha256_file(render_path)[:12]}",
        "02h_ae_scene_visual_qa",
        {
            "scene_number": job.scene_number,
            "duration_seconds": job.duration_seconds,
            "approved_direction": direction,
            "review_frame_timestamps_seconds": timestamps,
            "_local_image_paths": frame_paths,
        },
        "Review the attached frames from the rendered AE scene against approved_direction and its qa_assertions. "
        "Check that directed effects happen in the stated time windows, the uploaded action and identities remain "
        "consistent, and no unintended zoom, repeated motion, color/wardrobe drift, or visual damage appears. "
        "Return JSON only: {\"passed\":boolean,\"critical_issues\":[string],\"checks\":[{\"assertion\":string,\"passed\":boolean,\"evidence\":string}]}.",
    )
    if not isinstance(result, dict) or not isinstance(result.get("passed"), bool):
        raise AeReviewRequired("Scene visual QA did not return a valid pass/fail result")
    critical = result.get("critical_issues") if isinstance(result.get("critical_issues"), list) else []
    checks = result.get("checks") if isinstance(result.get("checks"), list) else []
    report = {"passed": result["passed"] and not critical, "critical_issues": critical,
              "checks": checks, "review_frame_timestamps_seconds": timestamps}
    if not report["passed"]:
        raise AeReviewRequired("AE scene visual QA failed: " + "; ".join(str(issue) for issue in critical[:6]))
    return report


def _clamp_float(value: Any, default: float, minimum: float, maximum: float) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        number = default
    return max(minimum, min(number, maximum))


def _color_value(value: Any, fallback: list[float]) -> list[float]:
    if isinstance(value, (list, tuple)) and len(value) >= 3:
        return [_clamp_float(value[index], fallback[index], 0.0, 1.0) for index in range(3)]
    return list(fallback)


def _target_value(value: Any, fallback: dict[str, Any]) -> dict[str, Any]:
    target = value if isinstance(value, dict) else {}
    return {
        "type": str(target.get("type") or fallback.get("type") or "focus"),
        "x": _clamp_float(target.get("x"), float(fallback.get("x") or 0.5), 0.05, 0.95),
        "y": _clamp_float(target.get("y"), float(fallback.get("y") or 0.5), 0.05, 0.95),
    }


def _effect_plan(job: SceneJob) -> dict[str, Any]:
    if job.plan_kind == "motion":
        plan = job.scene.get("ae_motion_plan") if isinstance(job.scene.get("ae_motion_plan"), dict) else {}
    else:
        plan = job.scene.get("ae_effect_plan") if isinstance(job.scene.get("ae_effect_plan"), dict) else {}
    palette = plan.get("palette") if isinstance(plan.get("palette"), dict) else {}
    motion = plan.get("motion") if isinstance(plan.get("motion"), dict) else {}
    targets = plan.get("targets") if isinstance(plan.get("targets"), list) else []
    primary_fallback = {"type": "focus", "x": 0.5, "y": 0.54}
    secondary_fallback = {"type": "energy", "x": 0.62, "y": 0.36}
    primary = _target_value(targets[0] if targets else plan.get("primary_target"), primary_fallback)
    secondary = _target_value(targets[1] if len(targets) > 1 else plan.get("secondary_target"), secondary_fallback)
    intensity = _clamp_float(plan.get("intensity"), 0.7, 0.25, 1.0)
    return {
        "preset": _safe_name(plan.get("preset"), job.preset),
        "plan_kind": job.plan_kind,
        "mood": str(plan.get("mood") or "dramatic_highlight"),
        "camera": str(plan.get("camera") or "slow_push_in"),
        "light": str(plan.get("light") or "cinematic_edge_light"),
        "vfx": [str(item) for item in (plan.get("vfx") if isinstance(plan.get("vfx"), list) else [])[:8]],
        "directorial_plan": plan.get("directorial_plan") if isinstance(plan.get("directorial_plan"), dict) else {},
        "primary": primary,
        "secondary": secondary,
        "primary_color": _color_value(palette.get("primary"), [0.58, 0.78, 1.0]),
        "accent_color": _color_value(palette.get("accent"), [0.25, 0.65, 1.0]),
        "flash_color": _color_value(palette.get("flash"), [0.86, 0.96, 1.0]),
        "intensity": min(intensity, 0.55) if job.plan_kind == "motion" else intensity,
        "push": _clamp_float(motion.get("push"), 0.05, -0.08, 0.12),
        "drift_x": _clamp_float(motion.get("drift_x"), -0.015, -0.06, 0.06),
        "drift_y": _clamp_float(motion.get("drift_y"), -0.008, -0.06, 0.06),
        "shake": _clamp_float(motion.get("shake"), 0.01, 0.0, 0.06),
        "transition_in": str(plan.get("transition_in") or "effect_reveal"),
        "transition_out": str(plan.get("transition_out") or "atmosphere_hold"),
    }


def _js_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=True)


def _write_jsx(job: SceneJob, input_image: Path, project_path: Path, render_path: Path, jsx_path: Path) -> None:
    preset = job.preset
    plan = _effect_plan(job)
    duration = job.duration_seconds
    width = DEFAULT_WIDTH
    height = DEFAULT_HEIGHT
    fps = DEFAULT_FPS
    # Coordinates are normalized for square output. The sword preset is tuned
    # for the generated wuxia ruin/sword composition but still renders safely
    # on any scene image.
    jsx = f'''
var imagePath = "{_ae_path(input_image)}";
var projectPath = "{_ae_path(project_path)}";
var renderPath = "{_ae_path(render_path)}";
var statusPath = "{_ae_path(jsx_path.with_suffix('.status.txt'))}";
var W = {width};
var H = {height};
var DUR = {duration:.3f};
var FPS = {fps};
var PLAN = {_js_json(plan)};
var INTENSITY = PLAN.intensity;
var PRIMARY = [PLAN.primary.x * W, PLAN.primary.y * H];
var SECONDARY = [PLAN.secondary.x * W, PLAN.secondary.y * H];
var PRIMARY_COLOR = PLAN.primary_color;
var ACCENT_COLOR = PLAN.accent_color;
var FLASH_COLOR = PLAN.flash_color;
app.exitAfterLaunchAndEval = true;

function px(value) {{
  return Math.max(1, Math.round(value));
}}

function writeStatus(value) {{
  var statusFile = new File(statusPath);
  if (statusFile.open("w")) {{
    statusFile.write(value);
    statusFile.close();
  }}
}}

function addFx(layer, matchName, label) {{
  var candidates = [matchName];
  if (label == "Glow") candidates = [matchName, "ADBE Glo2", "Glow"];
  if (label == "Gaussian Blur") candidates = [matchName, "ADBE Fast Blur", "ADBE Gaussian Blur", "Gaussian Blur"];
  if (label == "Wave Warp") candidates = [matchName, "ADBE Wave Warp", "Wave Warp"];
  if (label == "Page Turn") candidates = [matchName, "CC Page Turn", "ADBE Page Turn"];
  for (var i = 0; i < candidates.length; i++) {{
    try {{ return layer.property("Effects").addProperty(candidates[i]); }} catch (err) {{}}
  }}
  return null;
}}

function hasVfx(name) {{
  for (var i = 0; i < PLAN.vfx.length; i++) {{
    if (PLAN.vfx[i] == name) return true;
  }}
  return false;
}}

function scaled(value, minValue, maxValue) {{
  return minValue + (maxValue - minValue) * INTENSITY;
}}

function setOpacity(layer, t0, v0, t1, v1, t2, v2) {{
  var p = layer.property("Opacity");
  p.setValueAtTime(t0, v0);
  p.setValueAtTime(t1, v1);
  p.setValueAtTime(t2, v2);
}}

function makeStroke(comp, name, vertices, width, color, startOffset) {{
  var layer = comp.layers.addShape();
  layer.name = name;
  layer.property("Position").setValue([0, 0]);
  var group = layer.property("Contents").addProperty("ADBE Vector Group");
  var contents = group.property("Contents");
  var pathGroup = contents.addProperty("ADBE Vector Shape - Group");
  var shape = new Shape();
  shape.vertices = vertices;
  shape.inTangents = [];
  shape.outTangents = [];
  shape.closed = false;
  for (var i = 0; i < vertices.length; i++) {{
    shape.inTangents.push([0, 0]);
    shape.outTangents.push([0, 0]);
  }}
  pathGroup.property("Path").setValue(shape);
  var stroke = contents.addProperty("ADBE Vector Graphic - Stroke");
  stroke.property("Color").setValue(color);
  stroke.property("Stroke Width").setValue(width * scaled(0, 0.72, 1.22));
  stroke.property("Line Cap").setValue(2);
  var trim = contents.addProperty("ADBE Vector Filter - Trim");
  trim.property("Start").setValueAtTime(0, 72);
  trim.property("End").setValueAtTime(0, 74);
  trim.property("Start").setValueAtTime(0.8 + startOffset, 4);
  trim.property("End").setValueAtTime(1.2 + startOffset, 100);
  trim.property("Start").setValueAtTime(DUR, 0);
  trim.property("End").setValueAtTime(DUR, 100);
  layer.blendingMode = BlendingMode.ADD;
  setOpacity(layer, 0, 0, 0.8 + startOffset, 100, DUR, 42);
  addFx(layer, "ADBE Glo2", "Glow");
  addFx(layer, "ADBE Fast Blur", "Gaussian Blur");
  return layer;
}}

function makeEllipseRing(comp, name, pos, scale0, scale1, color, delay) {{
  var layer = comp.layers.addShape();
  layer.name = name;
  var group = layer.property("Contents").addProperty("ADBE Vector Group");
  var contents = group.property("Contents");
  var ellipse = contents.addProperty("ADBE Vector Shape - Ellipse");
  ellipse.property("Size").setValue([220, 70]);
  var stroke = contents.addProperty("ADBE Vector Graphic - Stroke");
  stroke.property("Color").setValue(color);
  stroke.property("Stroke Width").setValue(2 + Math.round(3 * INTENSITY));
  layer.property("Position").setValue(pos);
  layer.property("Rotation").setValue(-13);
  layer.property("Scale").setValueAtTime(delay, [scale0, scale0]);
  layer.property("Scale").setValueAtTime(delay + 1.2, [scale1, scale1]);
  setOpacity(layer, delay, 0, delay + 0.25, 70, delay + 1.2, 0);
  layer.blendingMode = BlendingMode.ADD;
  addFx(layer, "ADBE Glo2", "Glow");
  return layer;
}}

function makeMote(comp, idx, color) {{
  var origin = (idx % 3 == 0) ? PRIMARY : SECONDARY;
  var x = origin[0] + (((idx * 97) % 240) - 120);
  var y = origin[1] + (((idx * 53) % 240) - 120);
  var layer = comp.layers.addShape();
  layer.name = "ae_mote_" + idx;
  var group = layer.property("Contents").addProperty("ADBE Vector Group");
  var contents = group.property("Contents");
  var ellipse = contents.addProperty("ADBE Vector Shape - Ellipse");
  var size = 2 + (idx % 4);
  ellipse.property("Size").setValue([size, size]);
  var fill = contents.addProperty("ADBE Vector Graphic - Fill");
  fill.property("Color").setValue(color);
  layer.property("Position").setValueAtTime(0, [x, y]);
  layer.property("Position").setValueAtTime(DUR, [x + 45 - (idx % 9) * 10, y - scaled(0, 70, 155) - (idx % 7) * 16]);
  setOpacity(layer, 0, 0, 0.8 + (idx % 8) * 0.05, 72, DUR, 0);
  layer.blendingMode = BlendingMode.ADD;
}}

function makeFocusGlow(comp, name, pos, color, radius, delay) {{
  var layer = comp.layers.addShape();
  layer.name = name;
  var group = layer.property("Contents").addProperty("ADBE Vector Group");
  var contents = group.property("Contents");
  var ellipse = contents.addProperty("ADBE Vector Shape - Ellipse");
  ellipse.property("Size").setValue([radius, radius]);
  var fill = contents.addProperty("ADBE Vector Graphic - Fill");
  fill.property("Color").setValue(color);
  layer.property("Position").setValue(pos);
  layer.property("Scale").setValueAtTime(delay, [70, 70]);
  layer.property("Scale").setValueAtTime(Math.min(DUR, delay + 1.4), [135 + 45 * INTENSITY, 135 + 45 * INTENSITY]);
  setOpacity(layer, delay, 0, delay + 0.25, 38 + 30 * INTENSITY, Math.min(DUR, delay + 1.45), 0);
  layer.blendingMode = BlendingMode.ADD;
  addFx(layer, "ADBE Glo2", "Glow");
  addFx(layer, "ADBE Fast Blur", "Gaussian Blur");
  return layer;
}}

function makeLightSweep(comp, name, startPos, endPos, color, delay) {{
  var layer = comp.layers.addSolid(color, name, px(W), px(Math.max(24, 64 * INTENSITY)), 1, DUR);
  layer.blendingMode = BlendingMode.ADD;
  layer.property("Anchor Point").setValue([W / 2, px(Math.max(12, 32 * INTENSITY))]);
  layer.property("Position").setValueAtTime(delay, startPos);
  layer.property("Position").setValueAtTime(Math.min(DUR, delay + 1.2), endPos);
  layer.property("Rotation").setValue(-18);
  setOpacity(layer, delay, 0, delay + 0.25, 16 + 28 * INTENSITY, Math.min(DUR, delay + 1.2), 0);
  addFx(layer, "ADBE Fast Blur", "Gaussian Blur");
  return layer;
}}

function applyDepthProxy(comp, footage) {{
  var bgDepth = comp.layers.add(footage);
  bgDepth.name = "background_depth_plate";
  var bgScale = Math.max(W / footage.width, H / footage.height) * 105;
  bgDepth.property("Scale").setValueAtTime(0, [bgScale, bgScale]);
  bgDepth.property("Scale").setValueAtTime(DUR, [bgScale * (1.01 + INTENSITY * 0.012), bgScale * (1.01 + INTENSITY * 0.012)]);
  bgDepth.property("Position").setValueAtTime(0, [W / 2 + PLAN.drift_x * W * 0.12, H / 2 + PLAN.drift_y * H * 0.10]);
  bgDepth.property("Position").setValueAtTime(DUR, [W / 2 - PLAN.drift_x * W * 0.38, H / 2 - PLAN.drift_y * H * 0.25]);
  bgDepth.moveToEnd();
  addFx(bgDepth, "ADBE Fast Blur", "Gaussian Blur");

  var fg = comp.layers.add(footage);
  fg.name = "foreground_focus_depth_proxy";
  var fgScale = Math.max(W / footage.width, H / footage.height) * (104 + 5 * INTENSITY);
  fg.property("Scale").setValueAtTime(0, [fgScale, fgScale]);
  fg.property("Scale").setValueAtTime(DUR, [fgScale * (1.018 + Math.max(0, PLAN.push) * 0.12), fgScale * (1.018 + Math.max(0, PLAN.push) * 0.12)]);
  fg.property("Position").setValueAtTime(0, [W / 2 - PLAN.drift_x * W * 0.20, H / 2 - PLAN.drift_y * H * 0.18]);
  fg.property("Position").setValueAtTime(DUR, [W / 2 + PLAN.drift_x * W * 0.65, H / 2 + PLAN.drift_y * H * 0.50]);
  var mask = fg.Masks.addProperty("Mask");
  var shape = new Shape();
  var cx = PRIMARY[0], cy = PRIMARY[1];
  var rx = W * 0.28, ry = H * 0.34;
  shape.vertices = [[cx-rx, cy], [cx, cy-ry], [cx+rx, cy], [cx, cy+ry]];
  shape.inTangents = [[0,-ry*0.55],[-rx*0.55,0],[0,ry*0.55],[rx*0.55,0]];
  shape.outTangents = [[0,ry*0.55],[rx*0.55,0],[0,-ry*0.55],[-rx*0.55,0]];
  shape.closed = true;
  mask.property("Mask Path").setValue(shape);
  mask.property("Mask Feather").setValue([70, 70]);
  mask.property("Mask Opacity").setValue(72);
  return fg;
}}

function makeBreathingProxy(comp, footage) {{
  var breath = comp.layers.add(footage);
  breath.name = "puppet_proxy_breath_idle";
  var s = Math.max(W / footage.width, H / footage.height) * 100;
  breath.property("Scale").setValueAtTime(0, [s, s]);
  breath.property("Scale").setValueAtTime(Math.min(DUR, DUR * 0.45), [s * (1.006 + INTENSITY * 0.014), s * (1.012 + INTENSITY * 0.018)]);
  breath.property("Scale").setValueAtTime(DUR, [s * 1.003, s * 1.006]);
  breath.property("Position").setValue([W / 2, H / 2]);
  var mask = breath.Masks.addProperty("Mask");
  var shape = new Shape();
  var cx = PRIMARY[0], cy = PRIMARY[1] + H * 0.08;
  var rx = W * 0.20, ry = H * 0.30;
  shape.vertices = [[cx-rx, cy], [cx, cy-ry], [cx+rx, cy], [cx, cy+ry]];
  shape.inTangents = [[0,-ry*0.55],[-rx*0.55,0],[0,ry*0.55],[rx*0.55,0]];
  shape.outTangents = [[0,ry*0.55],[rx*0.55,0],[0,-ry*0.55],[-rx*0.55,0]];
  shape.closed = true;
  mask.property("Mask Path").setValue(shape);
  mask.property("Mask Feather").setValue([44, 44]);
  mask.property("Mask Opacity").setValue(44);
  setOpacity(breath, 0, 0, 0.3, 34 + 18 * INTENSITY, DUR, 22 + 12 * INTENSITY);
  addFx(breath, "ADBE Turbulent Displace", "Turbulent Displace");
  return breath;
}}

function makeHairClothWave(comp) {{
  for (var i = 0; i < 6; i++) {{
    var x = PRIMARY[0] - W * 0.13 + i * W * 0.052;
    var y = PRIMARY[1] - H * 0.28 + (i % 2) * 12;
    makeStroke(comp, "hair_cloth_wave_" + i, [[x, y], [x + 12 + i * 2, y + 55], [x - 8, y + 115]], 2 + (i % 2), PRIMARY_COLOR, 0.08 + i * 0.05);
  }}
}}

function makeSpeedLines(comp) {{
  var center = [PRIMARY[0], PRIMARY[1]];
  for (var i = 0; i < 18; i++) {{
    var a = (Math.PI * 2 * i) / 18;
    var r0 = W * 0.18;
    var r1 = W * (0.55 + (i % 4) * 0.045);
    var p0 = [center[0] + Math.cos(a) * r0, center[1] + Math.sin(a) * r0];
    var p1 = [center[0] + Math.cos(a) * r1, center[1] + Math.sin(a) * r1];
    makeStroke(comp, "speedline_burst_" + i, [p0, p1], 2 + (i % 3), FLASH_COLOR, 0.02 + (i % 5) * 0.025);
  }}
}}

function makeSpeechBubbleTypeOn(comp) {{
  var bubble = comp.layers.addShape();
  bubble.name = "speech_bubble_type_on_proxy";
  var group = bubble.property("Contents").addProperty("ADBE Vector Group");
  var contents = group.property("Contents");
  var rect = contents.addProperty("ADBE Vector Shape - Rect");
  rect.property("Size").setValue([px(W * 0.42), px(H * 0.13)]);
  rect.property("Roundness").setValue(28);
  var fill = contents.addProperty("ADBE Vector Graphic - Fill");
  fill.property("Color").setValue([0.96, 0.94, 0.86]);
  var stroke = contents.addProperty("ADBE Vector Graphic - Stroke");
  stroke.property("Color").setValue([0.08, 0.08, 0.08]);
  stroke.property("Stroke Width").setValue(2);
  bubble.property("Position").setValue([Math.min(W * 0.72, PRIMARY[0] + W * 0.16), Math.max(H * 0.16, PRIMARY[1] - H * 0.22)]);
  bubble.property("Scale").setValueAtTime(0, [84, 84]);
  bubble.property("Scale").setValueAtTime(0.28, [104, 104]);
  bubble.property("Scale").setValueAtTime(0.50, [100, 100]);
  setOpacity(bubble, 0, 0, 0.18, 86, DUR, 78);
  for (var i = 0; i < 3; i++) {{
    var dot = comp.layers.addShape();
    dot.name = "typing_dot_" + i;
    var dg = dot.property("Contents").addProperty("ADBE Vector Group");
    var dc = dg.property("Contents");
    var el = dc.addProperty("ADBE Vector Shape - Ellipse");
    el.property("Size").setValue([9, 9]);
    var df = dc.addProperty("ADBE Vector Graphic - Fill");
    df.property("Color").setValue([0.12, 0.12, 0.12]);
    dot.property("Position").setValue([bubble.property("Position").value[0] - 26 + i * 26, bubble.property("Position").value[1]]);
    setOpacity(dot, 0, 0, 0.34 + i * 0.18, 100, DUR, 70);
  }}
}}

function applyPageTurn(comp, layer) {{
  var fx = addFx(layer, "CC Page Turn", "Page Turn");
  if (fx) {{
    try {{
      fx.property("Fold Position").setValueAtTime(0, [W * 0.98, H * 0.08]);
      fx.property("Fold Position").setValueAtTime(Math.min(DUR, 1.15), [W * 0.80, H * 0.24]);
    }} catch (err) {{}}
  }} else {{
    layer.property("Rotation").setValueAtTime(0, 0);
    layer.property("Rotation").setValueAtTime(Math.min(DUR, 0.9), -1.8);
  }}
}}

app.beginSuppressDialogs();
try {{
  if (app.project) app.project.close(CloseOptions.DO_NOT_SAVE_CHANGES);
  app.newProject();
  var importOptions = new ImportOptions(new File(imagePath));
  if (/\\.psd$/i.test(imagePath) && importOptions.canImportAs(ImportAsType.COMP_CROPPED_LAYERS)) {{
    importOptions.importAs = ImportAsType.COMP_CROPPED_LAYERS;
  }}
  var footage = app.project.importFile(importOptions);
  var comp = app.project.items.addComp("ae_highlight_{_safe_name(preset)}", W, H, 1, DUR, FPS);
  comp.bgColor = [0, 0, 0];
  var layeredPsd = footage instanceof CompItem && footage.numLayers > 1;
  var bg = null;
  if (layeredPsd) {{
    for (var li = footage.numLayers; li >= 1; li--) {{
      var original = footage.layer(li);
      if (!original.source) continue;
      var separated = comp.layers.add(original.source);
      separated.name = original.name;
      var originalPosition = original.property("Position").value;
      if (/background|backdrop|배경/i.test(original.name) || bg == null) {{
        if (bg == null) bg = separated;
        separated.property("Position").setValue(originalPosition);
      }} else {{
        var direction = li % 2 == 0 ? 1 : -1;
        separated.property("Position").setValueAtTime(0, [originalPosition[0] - 12 * direction, originalPosition[1] + 5]);
        separated.property("Position").setValueAtTime(DUR, [originalPosition[0] + 14 * direction, originalPosition[1] - 5]);
        separated.property("Scale").setValueAtTime(0, [100,100]);
        separated.property("Scale").setValueAtTime(DUR, [104,104]);
      }}
    }}
  }}
  if (bg == null) {{
    bg = comp.layers.add(footage);
    bg.name = "source_scene";
  }}
  try {{ bg.audioEnabled = false; }} catch (audioErr) {{}}
  var scale = Math.max(W / footage.width, H / footage.height) * 100;
  var directorCameraMove = false;
  var directedOps = PLAN.directorial_plan.ae_operations || [];
  for (var opIndex = 0; opIndex < directedOps.length; opIndex++) {{
    if (directedOps[opIndex] == "camera_move") directorCameraMove = true;
  }}
  var reviewedUploadedClip = PLAN.directorial_plan.source_video_review_status == "reviewed";
  var startScale = scale * (reviewedUploadedClip && !directorCameraMove ? 1.0 : 1.015 + Math.max(0, PLAN.push) * 0.35);
  var endScale = scale * (reviewedUploadedClip && !directorCameraMove ? 1.0 : 1.015 + Math.abs(PLAN.push) + INTENSITY * 0.025);
  if (PLAN.push < 0) {{
    startScale = scale * (1.065 + INTENSITY * 0.025);
    endScale = scale * (1.02 + INTENSITY * 0.01);
  }}
  bg.property("Scale").setValueAtTime(0, [startScale, startScale]);
  bg.property("Scale").setValueAtTime(DUR, [endScale, endScale]);
  var focusX = PRIMARY[0], focusY = PRIMARY[1];
  var startRatio = startScale / scale, endRatio = endScale / scale;
  var startX = W / 2 - (focusX - W / 2) * (startRatio - 1) - PLAN.drift_x * W * 0.35;
  var startY = H / 2 - (focusY - H / 2) * (startRatio - 1) - PLAN.drift_y * H * 0.35;
  var endX = W / 2 - (focusX - W / 2) * (endRatio - 1) + PLAN.drift_x * W;
  var endY = H / 2 - (focusY - H / 2) * (endRatio - 1) + PLAN.drift_y * H;
  if (reviewedUploadedClip && !directorCameraMove) {{ startX = W / 2; startY = H / 2; endX = W / 2; endY = H / 2; }}
  bg.property("Position").setValueAtTime(0, [
    startX, startY
  ]);
  bg.property("Position").setValueAtTime(DUR, [
    endX, endY
  ]);
  if (PLAN.shake > 0.001) {{
    var shakePixels = Math.round(PLAN.shake * 170);
    bg.property("Position").setValueAtTime(0.32, [W / 2 + shakePixels, H / 2 - shakePixels * 0.35]);
    bg.property("Position").setValueAtTime(0.42, [W / 2 - shakePixels * 0.7, H / 2 + shakePixels * 0.25]);
    bg.property("Position").setValueAtTime(0.55, [W / 2 + PLAN.drift_x * W * 0.3, H / 2 + PLAN.drift_y * H * 0.3]);
  }}
  if (!layeredPsd && (hasVfx("layered_depth_proxy") || hasVfx("comic_parallax_camera") || hasVfx("depth_of_field"))) {{
    applyDepthProxy(comp, footage);
  }}
  if (!layeredPsd && hasVfx("puppet_breath_idle")) {{
    makeBreathingProxy(comp, footage);
  }}
  if (hasVfx("hair_cloth_wave")) {{
    makeHairClothWave(comp);
  }}
  if (hasVfx("page_turn_transition")) {{
    applyPageTurn(comp, bg);
  }}

  if (hasVfx("atmospheric_haze")) {{
    var fog = comp.layers.addSolid(ACCENT_COLOR, "fractal_moving_fog", W, H, 1, DUR);
    fog.blendingMode = BlendingMode.SCREEN;
    var hazeBeats = PLAN.directorial_plan.timed_beats || [];
    var hazeOpacity = fog.property("Opacity");
    hazeOpacity.setValueAtTime(0, 0);
    for (var hb = 0; hb < hazeBeats.length; hb++) {{
      if (hazeBeats[hb].action != "atmosphere_drift") continue;
      var ht = Number(hazeBeats[hb].start_seconds), he = Number(hazeBeats[hb].end_seconds);
      hazeOpacity.setValueAtTime(ht, 0);
      hazeOpacity.setValueAtTime(Math.min(he, ht + 0.25), 8 + 18 * INTENSITY);
      hazeOpacity.setValueAtTime(he, 0);
    }}
    var fractal = addFx(fog, "ADBE Fractal Noise", "Fractal Noise");
    if (fractal) {{
      try {{
        fractal.property("Contrast").setValue(105 + 95 * INTENSITY);
        fractal.property("Brightness").setValue(-60 + 24 * INTENSITY);
        fractal.property("Evolution").setValueAtTime(0, 0);
        fractal.property("Evolution").setValueAtTime(DUR, 160 + 210 * INTENSITY);
      }} catch (err1) {{}}
    }}
    addFx(fog, "ADBE Turbulent Displace", "Turbulent Displace");
    addFx(fog, "ADBE Fast Blur", "Gaussian Blur");
  }}
  if (hasVfx("warm_lantern_flicker")) {{
    var lantern = comp.layers.addSolid([1.0, 0.67, 0.34], "directed_warm_lantern_bounce", W, H, 1, DUR);
    lantern.blendingMode = BlendingMode.SCREEN;
    lantern.property("Opacity").setValueAtTime(0, 0);
    var visualBeats = PLAN.directorial_plan.timed_beats || [];
    for (var lb = 0; lb < visualBeats.length; lb++) {{
      if (visualBeats[lb].action != "light_flicker") continue;
      var lt = Number(visualBeats[lb].start_seconds), le = Number(visualBeats[lb].end_seconds);
      lantern.property("Opacity").setValueAtTime(lt, 0);
      lantern.property("Opacity").setValueAtTime(Math.min(le, lt + 0.08), 7);
      lantern.property("Opacity").setValueAtTime(le, 0);
    }}
  }}
  if (hasVfx("displacement_wave")) {{
    addFx(bg, "ADBE Wave Warp", "Wave Warp");
  }}
  if (PLAN.plan_kind == "effect") {{
  makeFocusGlow(comp, "targeted_primary_glow_" + PLAN.primary.type, PRIMARY, PRIMARY_COLOR, 170 + 130 * INTENSITY, 0.18);
  makeFocusGlow(comp, "targeted_secondary_glow_" + PLAN.secondary.type, SECONDARY, ACCENT_COLOR, 115 + 90 * INTENSITY, 0.55);
  makeLightSweep(comp, "targeted_light_sweep_" + PLAN.light, [PRIMARY[0] - W * 0.55, PRIMARY[1] + H * 0.18], [SECONDARY[0] + W * 0.42, SECONDARY[1] - H * 0.08], FLASH_COLOR, 0.65);

  var moonRay = comp.layers.addShape();
  moonRay.name = "volumetric_ray";
  moonRay.property("Position").setValue([0, 0]);
  var moonGroup = moonRay.property("Contents").addProperty("ADBE Vector Group");
  var moonContents = moonGroup.property("Contents");
  var rayPath = moonContents.addProperty("ADBE Vector Shape - Group");
  var rayShape = new Shape();
  rayShape.vertices = [[SECONDARY[0], SECONDARY[1] - 120], [W, SECONDARY[1] - 32], [W, SECONDARY[1] + 190], [PRIMARY[0] - 90, PRIMARY[1] + 70], [PRIMARY[0] + 60, PRIMARY[1] - 120]];
  rayShape.inTangents = [[0,0],[0,0],[0,0],[0,0],[0,0]];
  rayShape.outTangents = [[0,0],[0,0],[0,0],[0,0],[0,0]];
  rayShape.closed = true;
  rayPath.property("Path").setValue(rayShape);
  var rayFill = moonContents.addProperty("ADBE Vector Graphic - Fill");
  rayFill.property("Color").setValue(PRIMARY_COLOR);
  moonRay.blendingMode = BlendingMode.ADD;
  setOpacity(moonRay, 0, 0, 1.0, 8 + 20 * INTENSITY, DUR, 4 + 12 * INTENSITY);
  addFx(moonRay, "ADBE Fast Blur", "Gaussian Blur");

  if ("{preset}" == "anger_impact") {{
    makeStroke(comp, "red_impact_slash", [[PRIMARY[0]-260, PRIMARY[1]+170], [PRIMARY[0]-90, PRIMARY[1]+45], [SECONDARY[0], SECONDARY[1]], [SECONDARY[0]+210, SECONDARY[1]-130]], 18, PRIMARY_COLOR, 0.05);
    makeStroke(comp, "white_impact_core", [[PRIMARY[0]-190, PRIMARY[1]+110], [PRIMARY[0]-20, PRIMARY[1]+5], [SECONDARY[0]+110, SECONDARY[1]-60]], 6, FLASH_COLOR, 0.12);
    makeEllipseRing(comp, "impact_ring", PRIMARY, 25, 250, PRIMARY_COLOR, 0.35);
    makeSpeedLines(comp);
  }} else if ("{preset}" == "memory_ink_wash") {{
    makeStroke(comp, "ink_memory_reveal", [[PRIMARY[0]-310, PRIMARY[1]+130], [PRIMARY[0]-150, PRIMARY[1]+10], [PRIMARY[0]+60, PRIMARY[1]-40], [SECONDARY[0]+190, SECONDARY[1]-90]], 14, PRIMARY_COLOR, 0.1);
    makeEllipseRing(comp, "paper_memory_ring", PRIMARY, 30, 210, FLASH_COLOR, 0.45);
  }} else if ("{preset}" == "moon_fog_reveal") {{
    makeStroke(comp, "moonlight_cut", [[SECONDARY[0]-260, SECONDARY[1]+260], [SECONDARY[0]-100, SECONDARY[1]+145], [PRIMARY[0]-30, PRIMARY[1]+30], [PRIMARY[0]+120, PRIMARY[1]-75]], 7, PRIMARY_COLOR, 0.22);
    makeEllipseRing(comp, "fog_ring", SECONDARY, 35, 210, ACCENT_COLOR, 0.5);
  }} else {{
    makeStroke(comp, "blade_inner_blue_core", [[PRIMARY[0]-55, PRIMARY[1]-245], [PRIMARY[0]-28, PRIMARY[1]-90], [PRIMARY[0], PRIMARY[1]+70], [PRIMARY[0]+30, PRIMARY[1]+210]], 7, FLASH_COLOR, 0);
    makeStroke(comp, "blade_outer_white_qi", [[PRIMARY[0]-70, PRIMARY[1]-255], [PRIMARY[0]-38, PRIMARY[1]-90], [PRIMARY[0]+4, PRIMARY[1]+80], [PRIMARY[0]+40, PRIMARY[1]+225]], 18, PRIMARY_COLOR, 0.08);
    makeStroke(comp, "flying_sword_arc_01", [[PRIMARY[0]-135, PRIMARY[1]+20], [PRIMARY[0]+40, PRIMARY[1]-35], [SECONDARY[0], SECONDARY[1]], [SECONDARY[0]+155, SECONDARY[1]-90]], 5, FLASH_COLOR, 0.16);
    makeStroke(comp, "flying_sword_arc_02", [[PRIMARY[0]-165, PRIMARY[1]+105], [PRIMARY[0]+25, PRIMARY[1]+65], [SECONDARY[0]+75, SECONDARY[1]+35], [SECONDARY[0]+210, SECONDARY[1]+5]], 4, ACCENT_COLOR, 0.32);
    makeEllipseRing(comp, "qi_ring_ground_01", PRIMARY, 35, 185, PRIMARY_COLOR, 0.45);
    makeEllipseRing(comp, "qi_ring_ground_02", PRIMARY, 20, 245, ACCENT_COLOR, 1.15);
  }}
  if (hasVfx("speedline_burst")) {{
    makeSpeedLines(comp);
  }}
  }}
  if (hasVfx("speech_bubble_type_on")) {{
    makeSpeechBubbleTypeOn(comp);
  }}

  var moteCount = 0;
  if (hasVfx("warm_dust_motes")) {{
    moteCount = PLAN.plan_kind == "effect" ? Math.round(24 + 54 * INTENSITY) : Math.round(3 + 5 * INTENSITY);
  }}
  for (var i = 0; i < moteCount; i++) makeMote(comp, i, PRIMARY_COLOR);

  if (PLAN.plan_kind == "effect") {{
  var pulse = comp.layers.addSolid(FLASH_COLOR, "additive_pulse", W, H, 1, DUR);
  pulse.blendingMode = BlendingMode.ADD;
  setOpacity(pulse, 0, 0, 1.05, 6 + 16 * INTENSITY, 1.35, 0);
  pulse.property("Opacity").setValueAtTime(Math.min(DUR - 0.3, 2.4), 4 + 12 * INTENSITY);
  pulse.property("Opacity").setValueAtTime(Math.min(DUR, 2.75), 0);
  addFx(pulse, "ADBE Glo2", "Glow");

  var warp = comp.layers.addSolid([0.5, 0.5, 0.5], "heat_distortion_adjustment", W, H, 1, DUR);
  warp.adjustmentLayer = true;
  setOpacity(warp, 0, 0, 1.0, 8 + 42 * INTENSITY, DUR, 4 + 14 * INTENSITY);
  addFx(warp, "ADBE Turbulent Displace", "Turbulent Displace");
  }}

  if (hasVfx("subtle_vignette")) {{
    var vignette = comp.layers.addSolid([0, 0, 0], "ink_vignette", W, H, 1, DUR);
    vignette.blendingMode = BlendingMode.MULTIPLY;
    setOpacity(vignette, 0, 10 + 12 * INTENSITY, DUR / 2, 20 + 24 * INTENSITY, DUR, 14 + 20 * INTENSITY);
    addFx(vignette, "ADBE Radial Wipe", "Radial Wipe");
  }}

  var rqItem = app.project.renderQueue.items.add(comp);
  rqItem.outputModule(1).file = new File(renderPath);
  app.project.save(new File(projectPath));
  if (!new File(projectPath).exists) throw new Error("Project save returned without creating AEP: " + projectPath);
  writeStatus("success|" + projectPath + "|" + new Date().toUTCString());
  app.scheduleTask("app.quit()", 1200, false);
}} catch (err) {{
  writeStatus("error|" + err.toString() + "|line=" + err.line);
  app.scheduleTask("app.quit()", 1200, false);
  throw err;
}} finally {{
  app.endSuppressDialogs(false);
}}
'''
    jsx_path.with_suffix(".status.txt").unlink(missing_ok=True)
    jsx_path.write_text(jsx, encoding="utf-8")


def _ffmpeg_executable() -> str:
    try:
        import imageio_ffmpeg

        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return os.getenv("FFMPEG_PATH") or "ffmpeg"


def _log_tail(path: Path, limit: int = 4000) -> str:
    try:
        with path.open("rb") as log:
            log.seek(0, os.SEEK_END)
            log.seek(max(0, log.tell() - limit))
            return log.read().decode("utf-8", errors="replace").strip()
    except OSError:
        return ""


def _stop_command(process: subprocess.Popen[Any]) -> None:
    if process.poll() is not None:
        return
    try:
        process.terminate()
        process.wait(timeout=5)
    except (OSError, subprocess.TimeoutExpired):
        if process.poll() is None:
            try:
                process.kill()
                process.wait(timeout=5)
            except OSError:
                # It may have exited between poll() and kill().
                pass


def _run_checked(command: list[str], *, timeout: int = 900) -> None:
    """Run aerender with a durable log while checking for AE recovery UI."""
    log_path = Path(command[-1]).with_suffix(".aerender.log")
    log_path.parent.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    with log_path.open("wb") as log:
        process = subprocess.Popen(command, cwd=str(ROOT), stdout=log, stderr=subprocess.STDOUT)
        recovery_clicks = 0
        last_recovery_check = 0.0
        try:
            while process.poll() is None:
                now = time.monotonic()
                if now - started >= timeout:
                    raise AeWorkerError(
                        f"aerender timed out after {timeout}s; log={log_path}\n{_log_tail(log_path)}"
                    )
                if now - last_recovery_check >= 5:
                    last_recovery_check = now
                    if continue_crash_recovery():
                        recovery_clicks += 1
                        if recovery_clicks > 3:
                            raise AeRecoveryError(
                                f"AE crash-recovery dialog did not clear after 3 attempts; log={log_path}"
                            )
                try:
                    process.wait(timeout=min(2.0, max(0.1, timeout - (time.monotonic() - started))))
                except subprocess.TimeoutExpired:
                    pass
        except BaseException:
            _stop_command(process)
            raise
    if process.returncode != 0:
        raise AeWorkerError(
            f"aerender failed (exit={process.returncode}); log={log_path}\n{_log_tail(log_path)}"
        )


def _request_afterfx_close(process: subprocess.Popen[Any], *, timeout: float = 12) -> bool:
    """Close only the AE window started by this worker, without force-killing it."""
    if process.poll() is not None:
        return True
    if os.name == "nt":
        try:
            import ctypes
            from ctypes import wintypes

            user32 = ctypes.WinDLL("user32", use_last_error=True)
            enum_windows = user32.EnumWindows
            callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
            enum_windows.argtypes = [callback_type, wintypes.LPARAM]
            enum_windows.restype = wintypes.BOOL
            get_pid = user32.GetWindowThreadProcessId
            get_pid.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
            get_pid.restype = wintypes.DWORD
            post_message = user32.PostMessageW
            post_message.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
            post_message.restype = wintypes.BOOL
            target_pid = int(process.pid)
            sent = False

            @callback_type
            def visit(hwnd: int, _lparam: int) -> bool:
                nonlocal sent
                window_pid = wintypes.DWORD()
                get_pid(hwnd, ctypes.byref(window_pid))
                if window_pid.value == target_pid:
                    sent = bool(post_message(hwnd, 0x0010, 0, 0)) or sent  # WM_CLOSE
                return True

            enum_windows(visit, 0)
            if not sent:
                return False
            try:
                process.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                return False
            return True
        except Exception as exc:
            print(f"[AE] could not close worker-owned After Effects window: {exc}",
                  file=sys.stderr, flush=True)
            return False
    try:
        process.terminate()
        process.wait(timeout=timeout)
        return True
    except Exception:
        return False


def _run_afterfx_script(afterfx: Path, jsx_path: Path, project_path: Path, *, timeout: int = 240) -> None:
    """Run JSX in an isolated AE instance and wait for its explicit receipt.

    Without ``-m``, ``-r`` forwards the script to whichever interactive AE
    instance is already open. That instance may be busy with an unrelated
    project, so project creation must use a separate command-line instance.
    """
    candidate = afterfx
    if candidate.suffix.lower() == ".com":
        exe_path = candidate.with_suffix(".exe")
        if exe_path.is_file():
            candidate = exe_path

    status_path = jsx_path.with_suffix(".status.txt")
    status_path.unlink(missing_ok=True)
    log_path = jsx_path.with_name("afterfx-launch.log")
    with log_path.open("wb") as log:
        process = subprocess.Popen(
            [str(candidate), "-m", "-r", str(jsx_path)],
            cwd=str(ROOT),
            stdout=log,
            stderr=subprocess.STDOUT,
        )
        deadline = time.monotonic() + timeout
        last_recovery_check = 0.0
        recovery_clicks = 0
        try:
            while time.monotonic() < deadline:
                if status_path.is_file():
                    status_text = status_path.read_text(encoding="utf-8", errors="replace")
                    if status_text.startswith("error|"):
                        raise AeWorkerError(f"After Effects script failed: {status_text[:800]}")
                    if status_text.startswith("success|") and project_path.is_file():
                        if not _request_afterfx_close(process):
                            print(f"[AE] project saved; worker-owned AE window did not close: pid={process.pid}",
                                  file=sys.stderr, flush=True)
                        return
                now = time.monotonic()
                if now - last_recovery_check >= 5:
                    last_recovery_check = now
                    if continue_crash_recovery():
                        recovery_clicks += 1
                        if recovery_clicks > 3:
                            raise AeRecoveryError(
                                f"AE crash-recovery dialog did not clear after 3 attempts; log={log_path}"
                            )
                if process.poll() is not None and not status_path.exists():
                    raise AeWorkerError(
                        f"After Effects command exited without a JSX status receipt "
                        f"(exit={process.returncode}, log={log_path}): {_log_tail(log_path, 1200)}"
                    )
                time.sleep(1)
        except BaseException:
            _request_afterfx_close(process)
            raise
        if process.poll() is None:
            _request_afterfx_close(process)
    raise AeWorkerError(
        f"After Effects timed out without a JSX status receipt for {project_path}; "
        f"log={log_path}: {_log_tail(log_path, 1200)}"
    )


def _quality_report(job: SceneJob, mp4_path: Path) -> dict[str, Any]:
    if job.plan_kind == "motion":
        plan = job.scene.get("ae_motion_plan") if isinstance(job.scene.get("ae_motion_plan"), dict) else {}
    else:
        plan = job.scene.get("ae_effect_plan") if isinstance(job.scene.get("ae_effect_plan"), dict) else {}
    checks = plan.get("quality_checks") if isinstance(plan.get("quality_checks"), dict) else {}
    min_bytes = int(checks.get("min_output_bytes") or 1024)
    size = mp4_path.stat().st_size if mp4_path.exists() else 0
    return {
        "passed": size >= min_bytes,
        "file_size_bytes": size,
        "min_output_bytes": min_bytes,
        "targeted_effects_required": bool(checks.get("targeted_effects_required", True)),
        "failure_behavior": "retry_scene_without_substitute_render",
    }


def _manga_preflight(job: SceneJob, input_psd: Path) -> dict[str, Any]:
    """Verify the downloaded PSD itself, not just a possibly stale manifest."""
    if input_psd.suffix.lower() != ".psd":
        raise AeReviewRequired("Manga template needs a layered PSD; scene has only a flattened image")
    metadata = job.scene.get("metadata") if isinstance(job.scene.get("metadata"), dict) else {}
    asset = metadata.get("psd_layer_asset") if isinstance(metadata.get("psd_layer_asset"), dict) else {}
    if asset.get("qa_status") != "approved":
        raise AeReviewRequired("Manga PSD layer package has not passed layer review")
    expected_sha256 = str(asset.get("sha256") or "")
    if not re.fullmatch(r"[0-9a-f]{64}", expected_sha256):
        raise AeReviewRequired("Manga PSD approval is missing a valid SHA-256")
    if _sha256_file(input_psd) != expected_sha256:
        raise AeReviewRequired("Manga PSD differs from the approved layer package")
    try:
        from psd_tools import PSDImage

        psd = PSDImage.open(input_psd)
        layer_names = [str(layer.name).strip().lower() for layer in psd]
        dimensions = psd.size
        layer_centers = {}
        for layer in psd:
            bounds = layer.topil().convert("RGBA").getchannel("A").getbbox()
            if bounds:
                layer_centers[str(layer.name).strip().lower()] = [
                    round((bounds[0] + bounds[2]) / (2 * dimensions[0]), 6),
                    round((bounds[1] + bounds[3]) / (2 * dimensions[1]), 6),
                ]
    except Exception as exc:
        raise AeReviewRequired(f"Manga PSD could not be read: {exc}") from exc
    if dimensions != (DEFAULT_WIDTH, DEFAULT_HEIGHT):
        raise AeReviewRequired(f"Manga PSD dimensions {dimensions} do not match AE output "
                               f"{DEFAULT_WIDTH}x{DEFAULT_HEIGHT}")
    declared = {str(name).strip().lower() for name in (asset.get("layers") or [])}
    if set(layer_names) != declared:
        raise AeReviewRequired("Manga PSD layers differ from the approved layer manifest")
    verified_asset = {**asset, "local_path": str(input_psd), "layers": layer_names}
    report = validate_scene_plan(job.scene, verified_asset, job.duration_seconds)
    if not report["passed"]:
        raise AeReviewRequired("Manga scene plan failed preflight: " + "; ".join(report["errors"]))
    report["layer_centers"] = layer_centers
    return report


def _render_job(job: SceneJob, keep_workdir: bool = False) -> dict[str, Any]:
    afterfx = find_afterfx() or Path(DEFAULT_AFTERFX)
    aerender = find_aerender() or Path(DEFAULT_AERENDER)
    if not afterfx.is_file() or not aerender.is_file():
        raise AeWorkerError(f"After Effects executables not found: {afterfx} / {aerender}")

    template = template_for_scene(job.scene)
    direction_plan = job.scene.get("ae_effect_plan") if template else _effect_plan(job)
    identity = fingerprint({
        "version": 3 if template else 2, "source": job.source.__dict__, "kind": job.plan_kind,
        "preset": job.preset, "plan": direction_plan, "duration": job.duration_seconds,
        "width": DEFAULT_WIDTH, "height": DEFAULT_HEIGHT, "fps": DEFAULT_FPS,
    })
    workdir = worker_config.TEMP_DIR / "ae_highlight" / f"{_safe_name(job.topic_id)}-{job.scene_number:03d}-{job.plan_kind}-{identity}"
    checkpoint = Checkpoint(workdir / "checkpoint.json", identity)
    source_suffix = Path(job.source.path).suffix.lower()
    if source_suffix not in {".png", ".jpg", ".jpeg", ".psd", ".mp4", ".mov", ".webm", ".m4v"}:
        source_suffix = ".png"
    input_image = workdir / "input" / f"scene{source_suffix}"
    project_path = workdir / "project" / "ae_highlight.aep"
    mp4_path = workdir / "render" / "ae_highlight.mp4"
    jsx_path = workdir / "create_project.jsx"
    project_path.parent.mkdir(parents=True, exist_ok=True)
    mp4_path.parent.mkdir(parents=True, exist_ok=True)

    write_state("downloading", 10, _job_summary(job))
    if not valid_file(input_image):
        _download_gcs_file(job.source, input_image)
    checkpoint.mark("downloaded", {"path": str(input_image), "bytes": input_image.stat().st_size})

    # Uploaded clips are the visual ground truth. Finalize the director's
    # provisional plan against representative frames before creating an AEP;
    # this also invalidates a cached project when either the clip or its
    # reviewed direction changes.
    uploaded_video_direction = None
    uploaded_video_sha256 = ""
    if source_suffix in {".mp4", ".mov", ".webm", ".m4v"}:
        uploaded_video_direction, uploaded_video_sha256 = _review_uploaded_video_direction(job, input_image)
        direction_plan = _effect_plan(job)
        identity = fingerprint({
            "version": 4, "source": job.source.__dict__, "kind": job.plan_kind,
            "preset": job.preset, "plan": direction_plan, "duration": job.duration_seconds,
            "width": DEFAULT_WIDTH, "height": DEFAULT_HEIGHT, "fps": DEFAULT_FPS,
            "source_video_sha256": uploaded_video_sha256,
        })
        checkpoint = Checkpoint(workdir / "checkpoint.json", identity)

    plan_qa = _manga_preflight(job, input_image) if template else None
    if plan_qa:
        (workdir / "plan-qa.json").write_text(json.dumps(plan_qa, ensure_ascii=False, indent=2), encoding="utf-8")
    write_state("preparing", 25, _job_summary(job))
    saved_project = checkpoint.get("project_ready")
    project_reusable = (valid_file(project_path) and isinstance(saved_project, dict) and
                        saved_project.get("bytes") == project_path.stat().st_size)
    if not project_reusable:
        if project_path.exists():
            project_path.replace(project_path.with_name(project_path.name + ".stale-" + uuid.uuid4().hex))
        if template:
            write_manga_jsx(
                scene=job.scene, input_psd=input_image, project_path=project_path,
                render_path=mp4_path, jsx_path=jsx_path,
                comp_name=f"ae_highlight_{_safe_name(job.preset)}",
                width=DEFAULT_WIDTH, height=DEFAULT_HEIGHT, fps=DEFAULT_FPS,
                duration=job.duration_seconds,
                layer_centers=(plan_qa or {}).get("layer_centers"),
            )
        else:
            _write_jsx(job, input_image, project_path, mp4_path, jsx_path)
    write_state("preparing", 35, _job_summary(job))
    if not project_reusable:
        _run_afterfx_script(afterfx, jsx_path, project_path, timeout=240)
    if not valid_file(project_path):
        raise AeWorkerError("After Effects did not create a project file")
    checkpoint.mark("project_ready", {"path": str(project_path), "bytes": project_path.stat().st_size})
    write_state("rendering", 50, _job_summary(job))
    if not valid_mp4(mp4_path, job.duration_seconds * 0.8):
        try:
            _run_checked([str(aerender), "-project", str(project_path), "-comp", f"ae_highlight_{_safe_name(job.preset)}", "-output", str(mp4_path)], timeout=1200)
        except Exception:
            # A partially saved AEP can be large enough to pass a size check.
            # Rebuild it on the next attempt instead of looping on the same file.
            checkpoint.mark("project_ready", None)
            raise
    if not valid_mp4(mp4_path, job.duration_seconds * 0.8):
        raise AeWorkerError("After Effects render did not create a valid MP4")
    checkpoint.mark("rendered", {"path": str(mp4_path), "bytes": mp4_path.stat().st_size})
    scene_visual_qa = (_qa_uploaded_video_render(job, mp4_path, uploaded_video_direction)
                       if uploaded_video_direction is not None else None)
    quality = _quality_report(job, mp4_path)
    if not quality["passed"]:
        raise AeWorkerError(f"AE render quality check failed: {quality}")
    render_qa = validate_render(job.scene, mp4_path, fps=DEFAULT_FPS,
                                duration_seconds=job.duration_seconds) if template else None
    if render_qa:
        (workdir / "render-qa.json").write_text(json.dumps(render_qa, ensure_ascii=False, indent=2), encoding="utf-8")
        if not render_qa["passed"]:
            raise AeReviewRequired("Manga render failed QA: " + "; ".join(render_qa["errors"]))

    delivery = _scene_delivery(job.source_type, job.project_payload, job.structure, job.scene)
    if delivery == "local":
        write_state("ready_local", 88, _job_summary(job))
        location = {"storage_provider": "local", "local_path": str(mp4_path.resolve()),
                    "local_bytes": mp4_path.stat().st_size,
                    "local_mtime_ns": mp4_path.stat().st_mtime_ns, "media_url": ""}
    else:
        object_name = f"{'projects' if job.source_type == 'project' else 'topics'}/{job.topic_id}/ae/{job.plan_kind}/scene-{job.scene_number:03d}-{_safe_name(job.preset)}.mp4"
        write_state("uploading", 88, _job_summary(job))
        uploaded = checkpoint.get("uploaded")
        if isinstance(uploaded, dict) and uploaded.get("object_path") == object_name:
            bucket, gcs_path, media_url = uploaded["bucket"], uploaded["gcs_path"], uploaded["media_url"]
        else:
            bucket, gcs_path, media_url = _upload_gcs_file(mp4_path, object_name, "video/mp4")
            checkpoint.mark("uploaded", {"bucket": bucket, "gcs_path": gcs_path,
                                         "media_url": media_url, "object_path": object_name})
        location = {"storage_provider": "gcs", "bucket": bucket, "object_path": gcs_path,
                    "gcs_bucket": bucket, "gcs_path": gcs_path, "media_url": media_url}
    result = {
        **location,
        "plan_kind": job.plan_kind,
        "preset": job.preset,
        "duration_seconds": job.duration_seconds,
        "width": DEFAULT_WIDTH,
        "height": DEFAULT_HEIGHT,
        "fps": DEFAULT_FPS,
        "direction_plan": direction_plan,
        "directorial_plan": uploaded_video_direction,
        "source_video_sha256": uploaded_video_sha256,
        "scene_visual_qa": scene_visual_qa,
        "quality_report": quality,
        "manga_qa": {"plan": plan_qa, "render": render_qa} if template else None,
        "review_required": bool(render_qa and render_qa["review_required"]),
        "render_sha256": _sha256_file(mp4_path) if template else "",
        "review_local_path": str(mp4_path.resolve()) if template else "",
        "source_image": {"bucket": job.source.bucket, "object_path": job.source.path},
        "postprocess_mode": "after_effects",
        "local_workdir": str(workdir) if keep_workdir else "",
    }
    # Preserve the render so Premiere and a restarted worker can verify and reuse it.
    return result


def process_job(job: SceneJob, *, keep_workdir: bool = False) -> dict[str, Any]:
    write_state("claiming", 5, _job_summary(job))
    scene = job.structure["scenes"][job.scene_index]
    old_meta = scene.get("metadata") if isinstance(scene.get("metadata"), dict) else {}
    old_asset = old_meta.get(_asset_key(job)) if isinstance(old_meta.get(_asset_key(job)), dict) else {}
    attempts = int(old_asset.get("attempts") or 0) + 1
    _mark_scene(job, "rendering", started_at=_now(), preset=job.preset,
                attempts=attempts, next_retry_at=0)
    try:
        result = _render_job(job, keep_workdir=keep_workdir)
        scene = job.structure["scenes"][job.scene_index]
        metadata = scene.setdefault("metadata", {})
        asset_key = _asset_key(job)
        render_started_at = str((metadata.get(asset_key) or {}).get("started_at") or "")
        rendered_status = "review_pending" if result.get("review_required") else "ready"
        metadata[asset_key] = {
            **result,
            "status": rendered_status,
            "worker": os.getenv("AE_HIGHLIGHT_WORKER_ID") or worker_config.WORKER_INSTANCE_ID,
            "updated_at": _now(),
            "attempts": attempts,
        }
        scene[_status_key(job)] = rendered_status
        if result["media_url"] and rendered_status == "ready":
            scene[_video_url_key(job)] = result["media_url"]
            scene["video_url"] = result["media_url"]
        else:
            scene.pop(_video_url_key(job), None)
            if scene.get("video_url") in {result.get("media_url"), old_asset.get("media_url")} and scene.get("video_url"):
                scene.pop("video_url", None)
        scene["asset_status"] = rendered_status
        _patch_job_structure(
            job, expected_status="rendering",
            expected_started_at=render_started_at or None,
            asset_patch={**metadata[asset_key], "error": None, "next_retry_at": 0},
            next_status=rendered_status,
            media_url=result["media_url"] if rendered_status == "ready" else None,
            clear_media_url=rendered_status != "ready" or not bool(result["media_url"]),
        )
        state = _json_object(WORKER_STATE_FILE.read_text(encoding="utf-8")) if WORKER_STATE_FILE.exists() else {}
        state["last_success_at"] = time.time()
        WORKER_STATE_FILE.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")
        write_state("idle", 100, None, "")
        return result
    except AeSceneConflict:
        # A review or another render changed this scene. Never turn its newer
        # state into retry_wait from this stale worker snapshot.
        raise
    except Exception as exc:
        scene = job.structure["scenes"][job.scene_index]
        metadata = scene.setdefault("metadata", {})
        asset_key = _asset_key(job)
        retry_at = time.time() + min(1800, 30 * (2 ** min(attempts - 1, 6)))
        failed_status = "needs_attention" if isinstance(exc, (AeRecoveryError, AeReviewRequired)) or attempts >= MAX_ATTEMPTS else "retry_wait"
        metadata[asset_key] = {
            **(metadata.get(asset_key) if isinstance(metadata.get(asset_key), dict) else {}),
            "status": failed_status,
            "plan_kind": job.plan_kind,
            "worker": os.getenv("AE_HIGHLIGHT_WORKER_ID") or worker_config.WORKER_INSTANCE_ID,
            "updated_at": _now(),
            "error": str(exc)[:800],
            "attempts": attempts,
            "next_retry_at": retry_at if failed_status == "retry_wait" else 0,
        }
        failed_direction = job.scene.get("ae_directorial_plan")
        if isinstance(failed_direction, dict) and failed_direction.get("source_video_review_status") == "reviewed":
            metadata[asset_key]["directorial_plan"] = failed_direction
            metadata[asset_key]["source_video_sha256"] = failed_direction.get("source_video_sha256")
        scene[_status_key(job)] = failed_status
        _patch_job_structure(
            job, expected_status="rendering",
            expected_started_at=str(metadata[asset_key].get("started_at") or "") or None,
            asset_patch={
                "plan_kind": job.plan_kind,
                "worker": metadata[asset_key]["worker"],
                "updated_at": metadata[asset_key]["updated_at"],
                "error": metadata[asset_key]["error"],
                "attempts": attempts,
                "next_retry_at": metadata[asset_key]["next_retry_at"],
                **({"directorial_plan": metadata[asset_key]["directorial_plan"],
                    "source_video_sha256": metadata[asset_key]["source_video_sha256"]}
                   if metadata[asset_key].get("directorial_plan") else {}),
            }, next_status=failed_status,
        )
        write_state("failed", 0, _job_summary(job), str(exc)[:800])
        raise


def run_once(args: argparse.Namespace) -> int:
    write_state("polling", 0)
    rows = fetch_candidate_projects(args.topic_limit)
    if os.getenv("AE_RENDER_PREGEN_TOPICS") == "1" or args.topic_id:
        rows.extend(fetch_candidate_topics(args.topic_limit))
    jobs = _find_scene_jobs(rows, force=args.force)
    if args.topic_id:
        jobs = [job for job in jobs if job.topic_id == str(args.topic_id)]
    if args.scene_number:
        jobs = [job for job in jobs if job.scene_number == int(args.scene_number)]
    jobs = jobs[: args.max_scenes]
    if args.dry_run:
        print(json.dumps({"candidate_count": len(jobs), "jobs": [job.__dict__ | {"source": job.source.__dict__, "structure": "...", "scene": "..."} for job in jobs]}, ensure_ascii=False, indent=2))
        return 0
    completed = []
    errors: list[str] = []
    for job in jobs:
        if is_shutdown_requested("ae_highlight_worker"):
            break
        print(f"[AE] Rendering topic={job.topic_id} scene={job.scene_number} preset={job.preset}", flush=True)
        try:
            result = process_job(job, keep_workdir=args.keep_workdir)
            completed.append({"topic_id": job.topic_id, "scene_number": job.scene_number, "result": result})
            print(f"[AE] Ready scene={job.scene_number}: {result.get('media_url') or result.get('local_path')}", flush=True)
        except Exception as exc:
            errors.append(f"scene {job.scene_number}: {exc}")
            print(f"[AE] scene {job.scene_number} deferred: {exc}", file=sys.stderr, flush=True)
    if not jobs:
        write_state("idle", 0)
    print(json.dumps({"completed": len(completed), "errors": errors, "items": completed}, ensure_ascii=False))
    return 1 if errors and not args.loop else 0


def run_loop(args: argparse.Namespace) -> int:
    clear_shutdown_flag("ae_highlight_worker")
    print("[AE] highlight worker started", flush=True)
    while not is_shutdown_requested("ae_highlight_worker"):
        try:
            run_once(args)
        except KeyboardInterrupt:
            raise
        except Exception as exc:
            print(f"[AE] tick failed: {exc}", file=sys.stderr, flush=True)
        deadline = time.time() + args.poll_seconds
        while time.time() < deadline and not is_shutdown_requested("ae_highlight_worker"):
            time.sleep(min(1.0, max(0.0, deadline - time.time())))
    write_state("stopped", 0, None, "")
    clear_shutdown_flag("ae_highlight_worker")
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Poll GCS-backed topic scene images and render AE highlight clips.")
    parser.add_argument("--loop", action="store_true", help="Run continuously instead of one polling pass.")
    parser.add_argument("--topic-id", default="", help="Limit to one topics_queue id.")
    parser.add_argument("--scene-number", type=int, default=0, help="Limit to one scene number.")
    parser.add_argument("--topic-limit", type=int, default=DEFAULT_TOPIC_LIMIT)
    parser.add_argument("--max-scenes", type=int, default=DEFAULT_MAX_SCENES_PER_TICK)
    parser.add_argument("--poll-seconds", type=float, default=DEFAULT_POLL_SECONDS)
    parser.add_argument("--force", action="store_true", help="Re-render even if ae_video_url already exists.")
    parser.add_argument("--dry-run", action="store_true", help="Show matching jobs without rendering.")
    parser.add_argument("--keep-workdir", action="store_true", help="Keep local AE job files for debugging.")
    args, _unknown = parser.parse_known_args()
    if "--role" in sys.argv and not args.dry_run:
        args.loop = True
    return args


def main() -> int:
    args = parse_args()
    return run_loop(args) if args.loop else run_once(args)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("[AE] stopped", flush=True)
        raise SystemExit(130)
