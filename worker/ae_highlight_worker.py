"""After Effects highlight renderer for prepared topic scene images.

This worker polls topics_queue for scenes with ae_effect_plan.enabled=true,
downloads the scene image from GCS, renders a short AE CS6-compatible effect
clip, uploads the MP4 back to GCS, and writes the result to
pregenerated_structure.
"""
from __future__ import annotations

import argparse
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
from shutdown_flag import clear_shutdown_flag, is_shutdown_requested


ROOT = Path(__file__).resolve().parent.parent
STATE_DIR = worker_config.STATE_DIR / "ae_highlight"
STATE_DIR.mkdir(parents=True, exist_ok=True)
WORKER_STATE_FILE = worker_config.STATE_DIR / "ae_highlight_worker.json"

DEFAULT_AFTERFX = r"C:\Program Files\Adobe\Adobe After Effects CS6\Support Files\AfterFX.exe"
DEFAULT_AERENDER = r"C:\Program Files\Adobe\Adobe After Effects CS6\Support Files\aerender.exe"
DEFAULT_BUCKET = os.getenv("GCS_BUCKET_NAME") or "air-studio-prod"
DEFAULT_WIDTH = int(os.getenv("AE_HIGHLIGHT_WIDTH", "720"))
DEFAULT_HEIGHT = int(os.getenv("AE_HIGHLIGHT_HEIGHT", "720"))
DEFAULT_FPS = int(os.getenv("AE_HIGHLIGHT_FPS", "24"))
DEFAULT_POLL_SECONDS = float(os.getenv("AE_HIGHLIGHT_POLL_SECONDS", "20"))
DEFAULT_TOPIC_LIMIT = int(os.getenv("AE_HIGHLIGHT_TOPIC_LIMIT", "20"))
DEFAULT_MAX_SCENES_PER_TICK = int(os.getenv("AE_HIGHLIGHT_MAX_SCENES_PER_TICK", "3"))


class AeWorkerError(RuntimeError):
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
    asset = metadata.get("cowork_image_asset") if isinstance(metadata.get("cowork_image_asset"), dict) else {}
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


def _find_scene_jobs(rows: list[dict[str, Any]], force: bool = False) -> list[SceneJob]:
    jobs: list[SceneJob] = []
    for row in rows:
        topic_id = str(row.get("id") or "")
        structure = _json_object(row.get("pregenerated_structure"))
        scenes = structure.get("scenes")
        if not topic_id or not isinstance(scenes, list):
            continue
        for index, scene in enumerate(scenes):
            if not isinstance(scene, dict):
                continue
            render_plan = _render_plan_from_scene(scene)
            if not render_plan:
                continue
            plan_kind, plan = render_plan
            meta = scene.get("metadata") if isinstance(scene.get("metadata"), dict) else {}
            asset_key = _asset_key(plan_kind)
            url_key = _video_url_key(plan_kind)
            ae_meta = meta.get(asset_key) if isinstance(meta.get(asset_key), dict) else {}
            if not force and (ae_meta.get("status") == "ready" or scene.get(url_key)):
                continue
            if not force and ae_meta.get("status") == "rendering":
                started = str(ae_meta.get("started_at") or "")
                # A stale rendering marker can be retried by restarting with --force.
                if started:
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
                    topic_title=str(row.get("generated_title") or row.get("topic") or topic_id),
                    structure=structure,
                    scene_index=index,
                    scene=scene,
                    scene_number=scene_number,
                    plan_kind=plan_kind,
                    preset=_safe_name(plan.get("preset"), "wuxia_sword_aura"),
                    duration_seconds=max(1.0, min(duration, 12.0)),
                    source=source,
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


def patch_topic_structure(topic_id: str, structure: dict[str, Any]) -> None:
    base_url, headers = _supabase()
    _request(
        "PATCH",
        f"{base_url}/rest/v1/topics_queue?id=eq.{quote(str(topic_id), safe='')}",
        {**headers, "Content-Type": "application/json", "Prefer": "return=minimal"},
        json={"pregenerated_structure": structure},
    )


def _mark_scene(job: SceneJob, status: str, **extra: Any) -> None:
    scene = job.structure["scenes"][job.scene_index]
    metadata = scene.setdefault("metadata", {})
    asset_key = _asset_key(job)
    metadata[asset_key] = {
        **(metadata.get(asset_key) if isinstance(metadata.get(asset_key), dict) else {}),
        "status": status,
        "plan_kind": job.plan_kind,
        "worker": os.getenv("AE_HIGHLIGHT_WORKER_ID") or worker_config.WORKER_INSTANCE_ID,
        "updated_at": _now(),
        **extra,
    }
    scene[_status_key(job)] = status
    patch_topic_structure(job.topic_id, job.structure)


def _job_summary(job: SceneJob) -> dict[str, Any]:
    return {
        "job_id": f"ae:{job.plan_kind}:{job.topic_id}:{job.scene_number}",
        "job_type": "render_ae_highlight" if job.plan_kind == "effect" else "render_ae_motion",
        "source": "topics_queue",
        "status": "rendering",
        "project_name": job.topic_title,
        "scene_number": job.scene_number,
        "plan_kind": job.plan_kind,
        "preset": job.preset,
        "progress_message": f"AE {job.plan_kind} scene {job.scene_number} ({job.preset})",
    }


def _ae_path(value: Path) -> str:
    return str(value.resolve()).replace("\\", "/")


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


def _write_jsx(job: SceneJob, input_image: Path, project_path: Path, avi_path: Path, jsx_path: Path) -> None:
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
var renderPath = "{_ae_path(avi_path)}";
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

function addFx(layer, matchName, label) {{
  var candidates = [matchName];
  if (label == "Glow") candidates = [matchName, "ADBE Glo2", "Glow"];
  if (label == "Gaussian Blur") candidates = [matchName, "ADBE Fast Blur", "ADBE Gaussian Blur", "Gaussian Blur"];
  for (var i = 0; i < candidates.length; i++) {{
    try {{ return layer.property("Effects").addProperty(candidates[i]); }} catch (err) {{}}
  }}
  return null;
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
  var layer = comp.layers.addSolid(color, name, W, Math.max(24, 64 * INTENSITY), 1, DUR);
  layer.blendingMode = BlendingMode.ADD;
  layer.property("Anchor Point").setValue([W / 2, Math.max(12, 32 * INTENSITY)]);
  layer.property("Position").setValueAtTime(delay, startPos);
  layer.property("Position").setValueAtTime(Math.min(DUR, delay + 1.2), endPos);
  layer.property("Rotation").setValue(-18);
  setOpacity(layer, delay, 0, delay + 0.25, 16 + 28 * INTENSITY, Math.min(DUR, delay + 1.2), 0);
  addFx(layer, "ADBE Fast Blur", "Gaussian Blur");
  return layer;
}}

app.beginSuppressDialogs();
try {{
  if (app.project) app.project.close(CloseOptions.DO_NOT_SAVE_CHANGES);
  app.newProject();
  var footage = app.project.importFile(new ImportOptions(new File(imagePath)));
  var comp = app.project.items.addComp("ae_highlight_{_safe_name(preset)}", W, H, 1, DUR, FPS);
  comp.bgColor = [0, 0, 0];
  var bg = comp.layers.add(footage);
  bg.name = "source_scene";
  var scale = Math.max(W / footage.width, H / footage.height) * 100;
  var startScale = scale * (1.015 + Math.max(0, PLAN.push) * 0.35);
  var endScale = scale * (1.015 + Math.abs(PLAN.push) + INTENSITY * 0.025);
  if (PLAN.push < 0) {{
    startScale = scale * (1.065 + INTENSITY * 0.025);
    endScale = scale * (1.02 + INTENSITY * 0.01);
  }}
  bg.property("Scale").setValueAtTime(0, [startScale, startScale]);
  bg.property("Scale").setValueAtTime(DUR, [endScale, endScale]);
  bg.property("Position").setValueAtTime(0, [W / 2 - PLAN.drift_x * W * 0.35, H / 2 - PLAN.drift_y * H * 0.35]);
  bg.property("Position").setValueAtTime(DUR, [W / 2 + PLAN.drift_x * W, H / 2 + PLAN.drift_y * H]);
  if (PLAN.shake > 0.001) {{
    var shakePixels = Math.round(PLAN.shake * 170);
    bg.property("Position").setValueAtTime(0.32, [W / 2 + shakePixels, H / 2 - shakePixels * 0.35]);
    bg.property("Position").setValueAtTime(0.42, [W / 2 - shakePixels * 0.7, H / 2 + shakePixels * 0.25]);
    bg.property("Position").setValueAtTime(0.55, [W / 2 + PLAN.drift_x * W * 0.3, H / 2 + PLAN.drift_y * H * 0.3]);
  }}

  var fog = comp.layers.addSolid(ACCENT_COLOR, "fractal_moving_fog", W, H, 1, DUR);
  fog.blendingMode = BlendingMode.SCREEN;
  setOpacity(fog, 0, 0, 1.0, 12 + 30 * INTENSITY, DUR, 8 + 22 * INTENSITY);
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

  var moteCount = Math.round(24 + 54 * INTENSITY);
  for (var i = 0; i < moteCount; i++) makeMote(comp, i, PRIMARY_COLOR);

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

  var vignette = comp.layers.addSolid([0, 0, 0], "ink_vignette", W, H, 1, DUR);
  vignette.blendingMode = BlendingMode.MULTIPLY;
  setOpacity(vignette, 0, 10 + 12 * INTENSITY, DUR / 2, 20 + 24 * INTENSITY, DUR, 14 + 20 * INTENSITY);
  addFx(vignette, "ADBE Radial Wipe", "Radial Wipe");

  var rqItem = app.project.renderQueue.items.add(comp);
  rqItem.outputModule(1).file = new File(renderPath);
  app.project.save(new File(projectPath));
}} finally {{
  app.endSuppressDialogs(false);
}}
'''
    jsx_path.write_text(jsx, encoding="utf-8")


def _ffmpeg_executable() -> str:
    try:
        import imageio_ffmpeg

        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return os.getenv("FFMPEG_PATH") or "ffmpeg"


def _run_checked(command: list[str], *, timeout: int = 900) -> None:
    result = subprocess.run(command, cwd=str(ROOT), text=True, capture_output=True, timeout=timeout)
    if result.returncode != 0:
        detail = "\n".join(part for part in (result.stdout[-1500:], result.stderr[-2500:]) if part)
        raise AeWorkerError(f"command failed ({result.returncode}): {' '.join(command)}\n{detail}")


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
        "fallback_on_failure": checks.get("fallback_on_failure") or "ffmpeg_basic_motion",
    }


def _render_job(job: SceneJob, keep_workdir: bool = False) -> dict[str, Any]:
    afterfx = Path(os.getenv("AE_AFTERFX_PATH") or DEFAULT_AFTERFX)
    aerender = Path(os.getenv("AE_AERENDER_PATH") or DEFAULT_AERENDER)
    if not afterfx.is_file() or not aerender.is_file():
        raise AeWorkerError(f"After Effects CS6 executables not found: {afterfx} / {aerender}")

    workdir = worker_config.TEMP_DIR / "ae_highlight" / f"{job.topic_id}-{job.scene_number:03d}-{uuid.uuid4().hex[:8]}"
    input_image = workdir / "input" / "scene.png"
    project_path = workdir / "project" / "ae_highlight.aep"
    avi_path = workdir / "render" / "ae_highlight.avi"
    mp4_path = workdir / "render" / "ae_highlight.mp4"
    jsx_path = workdir / "create_project.jsx"
    project_path.parent.mkdir(parents=True, exist_ok=True)
    avi_path.parent.mkdir(parents=True, exist_ok=True)

    write_state("downloading", 10, _job_summary(job))
    _download_gcs_file(job.source, input_image)
    write_state("preparing", 25, _job_summary(job))
    _write_jsx(job, input_image, project_path, avi_path, jsx_path)
    write_state("preparing", 35, _job_summary(job))
    _run_checked([str(afterfx), "-r", str(jsx_path)], timeout=240)
    if not project_path.is_file():
        raise AeWorkerError("After Effects did not create a project file")
    write_state("rendering", 50, _job_summary(job))
    _run_checked([str(aerender), "-project", str(project_path), "-comp", f"ae_highlight_{_safe_name(job.preset)}", "-output", str(avi_path)], timeout=1200)
    if not avi_path.is_file() or avi_path.stat().st_size < 1024:
        raise AeWorkerError("After Effects render did not create a valid AVI")

    ffmpeg = _ffmpeg_executable()
    write_state("transcoding", 75, _job_summary(job))
    _run_checked(
        [
            ffmpeg,
            "-y",
            "-i",
            str(avi_path),
            "-an",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-movflags",
            "+faststart",
            "-crf",
            os.getenv("AE_HIGHLIGHT_CRF", "19"),
            str(mp4_path),
        ],
        timeout=900,
    )
    if not mp4_path.is_file() or mp4_path.stat().st_size < 1024:
        raise AeWorkerError("FFmpeg transcode did not create a valid MP4")
    quality = _quality_report(job, mp4_path)
    if not quality["passed"]:
        raise AeWorkerError(f"AE render quality check failed: {quality}")

    object_name = f"topics/{job.topic_id}/ae/{job.plan_kind}/scene-{job.scene_number:03d}-{_safe_name(job.preset)}.mp4"
    write_state("uploading", 88, _job_summary(job))
    bucket, gcs_path, media_url = _upload_gcs_file(mp4_path, object_name, "video/mp4")
    result = {
        "storage_provider": "gcs",
        "bucket": bucket,
        "object_path": gcs_path,
        "gcs_bucket": bucket,
        "gcs_path": gcs_path,
        "media_url": media_url,
        "plan_kind": job.plan_kind,
        "preset": job.preset,
        "duration_seconds": job.duration_seconds,
        "width": DEFAULT_WIDTH,
        "height": DEFAULT_HEIGHT,
        "fps": DEFAULT_FPS,
        "direction_plan": _effect_plan(job),
        "quality_report": quality,
        "source_image": {"bucket": job.source.bucket, "object_path": job.source.path},
        "local_workdir": str(workdir) if keep_workdir else "",
    }
    if not keep_workdir:
        shutil.rmtree(workdir, ignore_errors=True)
    return result


def process_job(job: SceneJob, *, keep_workdir: bool = False) -> dict[str, Any]:
    write_state("claiming", 5, _job_summary(job))
    _mark_scene(job, "rendering", started_at=_now(), preset=job.preset)
    try:
        result = _render_job(job, keep_workdir=keep_workdir)
        scene = job.structure["scenes"][job.scene_index]
        metadata = scene.setdefault("metadata", {})
        asset_key = _asset_key(job)
        metadata[asset_key] = {
            **result,
            "status": "ready",
            "worker": os.getenv("AE_HIGHLIGHT_WORKER_ID") or worker_config.WORKER_INSTANCE_ID,
            "updated_at": _now(),
        }
        scene[_status_key(job)] = "ready"
        scene[_video_url_key(job)] = result["media_url"]
        scene["video_url"] = result["media_url"]
        scene["asset_status"] = "ready"
        patch_topic_structure(job.topic_id, job.structure)
        state = _json_object(WORKER_STATE_FILE.read_text(encoding="utf-8")) if WORKER_STATE_FILE.exists() else {}
        state["last_success_at"] = time.time()
        WORKER_STATE_FILE.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")
        write_state("idle", 100, None, "")
        return result
    except Exception as exc:
        scene = job.structure["scenes"][job.scene_index]
        metadata = scene.setdefault("metadata", {})
        asset_key = _asset_key(job)
        metadata[asset_key] = {
            **(metadata.get(asset_key) if isinstance(metadata.get(asset_key), dict) else {}),
            "status": "failed",
            "plan_kind": job.plan_kind,
            "worker": os.getenv("AE_HIGHLIGHT_WORKER_ID") or worker_config.WORKER_INSTANCE_ID,
            "updated_at": _now(),
            "error": str(exc)[:800],
        }
        scene[_status_key(job)] = "failed"
        patch_topic_structure(job.topic_id, job.structure)
        write_state("failed", 0, _job_summary(job), str(exc)[:800])
        raise


def run_once(args: argparse.Namespace) -> int:
    write_state("polling", 0)
    rows = fetch_candidate_topics(args.topic_limit)
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
    for job in jobs:
        print(f"[AE] Rendering topic={job.topic_id} scene={job.scene_number} preset={job.preset}", flush=True)
        result = process_job(job, keep_workdir=args.keep_workdir)
        completed.append({"topic_id": job.topic_id, "scene_number": job.scene_number, "result": result})
        print(f"[AE] Uploaded scene={job.scene_number}: {result['media_url']}", flush=True)
    if not jobs:
        write_state("idle", 0)
    print(json.dumps({"completed": len(completed), "items": completed}, ensure_ascii=False))
    return 0


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
