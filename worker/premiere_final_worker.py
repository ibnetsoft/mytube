"""Premiere final assembly package worker for submitted user projects.

This worker targets a modern GPU Windows host with current Premiere Pro and
After Effects installed. It keeps Premiere automation behind a package boundary:
the worker downloads/points at approved assets, creates an FCPXML timeline,
SRT subtitle file, Premiere automation manifest, and a JSX bridge script, then
records that package back onto the project. A UXP/AME export bridge can consume
the manifest on the Adobe host without changing the user-web data model.
"""
from __future__ import annotations

import argparse
import json
import mimetypes
import os
import re
import subprocess
import sys
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from html import escape
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, quote, unquote, urlparse

import requests

import worker_config
from adobe_tools import capability_report, find_media_encoder, find_premiere
from shutdown_flag import clear_shutdown_flag, is_shutdown_requested


WORKER_NAME = "premiere_final_worker"
STATE_FILE = worker_config.STATE_DIR / f"{WORKER_NAME}.json"
PACKAGE_ROOT = worker_config.TEMP_DIR / "premiere_final"
DEFAULT_BUCKET = os.getenv("GCS_BUCKET_NAME") or "air-studio-prod"
DEFAULT_FPS = int(os.getenv("PREMIERE_FINAL_FPS", "30"))
DEFAULT_WIDTH = int(os.getenv("PREMIERE_FINAL_WIDTH", "1920"))
DEFAULT_HEIGHT = int(os.getenv("PREMIERE_FINAL_HEIGHT", "1080"))
DEFAULT_POLL_SECONDS = float(os.getenv("PREMIERE_FINAL_POLL_SECONDS", "30"))
DEFAULT_PROJECT_LIMIT = int(os.getenv("PREMIERE_FINAL_PROJECT_LIMIT", "10"))


class PremiereWorkerError(RuntimeError):
    pass


@dataclass(frozen=True)
class GcsRef:
    bucket: str
    path: str


@dataclass(frozen=True)
class ProjectJob:
    project_id: str
    title: str
    row: dict[str, Any]
    payload: dict[str, Any]
    structure: dict[str, Any]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_name(value: Any, fallback: str = "item") -> str:
    text = str(value or "").strip().lower()
    text = re.sub(r"[^a-z0-9._-]+", "-", text)
    text = re.sub(r"-{2,}", "-", text).strip("-._")
    return text[:90] or fallback


def _json_object(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str) and value.strip():
        parsed = json.loads(value)
        if isinstance(parsed, dict):
            return parsed
    return {}


def write_state(status: str, progress: int = 0, current_job: dict[str, Any] | None = None, last_error: str | None = None) -> None:
    previous = {}
    if STATE_FILE.exists():
        try:
            previous = json.loads(STATE_FILE.read_text(encoding="utf-8"))
        except Exception:
            previous = {}
    STATE_FILE.write_text(
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
                "capability": capability_report(),
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


def _supabase() -> tuple[str, dict[str, str]]:
    url = (os.getenv("NEXT_PUBLIC_SUPABASE_URL") or os.getenv("SUPABASE_URL") or "").rstrip("/")
    key = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or ""
    if not url or not key:
        raise PremiereWorkerError("NEXT_PUBLIC_SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY are required")
    return url, {"apikey": key, "Authorization": f"Bearer {key}"}


def _request(method: str, url: str, headers: dict[str, str], **kwargs: Any) -> requests.Response:
    response = requests.request(method, url, headers=headers, timeout=90, **kwargs)
    if not response.ok:
        raise PremiereWorkerError(f"Supabase request failed ({response.status_code}): {response.text[:500]}")
    return response


def _gcs_credentials():
    client_email = os.getenv("GCS_CLIENT_EMAIL") or os.getenv("GOOGLE_CLIENT_EMAIL") or ""
    private_key = os.getenv("GCS_PRIVATE_KEY") or os.getenv("GOOGLE_PRIVATE_KEY") or ""
    project_id = os.getenv("GCS_PROJECT_ID") or os.getenv("GOOGLE_CLOUD_PROJECT") or "air-studio-prod"
    bucket = os.getenv("GCS_BUCKET_NAME") or DEFAULT_BUCKET
    if not (client_email and private_key and bucket):
        raise PremiereWorkerError("GCS credentials are required for Premiere final packaging")
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
        raise PremiereWorkerError("GCS object path is empty")
    response = requests.get(
        f"https://storage.googleapis.com/storage/v1/b/{quote(bucket, safe='')}/o/"
        f"{quote(clean_path, safe='')}?alt=media",
        headers={"Authorization": f"Bearer {creds.token}"},
        timeout=300,
    )
    if response.status_code != 200:
        raise PremiereWorkerError(f"GCS download failed ({response.status_code}): {response.text[:300]}")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(response.content)


def _upload_gcs_file(file_path: Path, object_path: str, mime_type: str) -> tuple[str, str, str]:
    creds, bucket = _gcs_credentials()
    clean_path = str(object_path or "").strip().replace("\\", "/").lstrip("/")
    if not clean_path:
        raise PremiereWorkerError("GCS object path is empty")
    with file_path.open("rb") as handle:
        response = requests.post(
            f"https://storage.googleapis.com/upload/storage/v1/b/{quote(bucket, safe='')}/o"
            f"?uploadType=media&name={quote(clean_path, safe='')}",
            headers={"Authorization": f"Bearer {creds.token}", "Content-Type": mime_type},
            data=handle,
            timeout=600,
        )
    if response.status_code not in (200, 201):
        raise PremiereWorkerError(f"GCS upload failed ({response.status_code}): {response.text[:300]}")
    return bucket, clean_path, f"/api/std/assets/gcs-file?bucket={quote(bucket, safe='')}&path={quote(clean_path, safe='')}"


def _gcs_ref_from_url(value: str) -> GcsRef | None:
    text = str(value or "").strip()
    if text.startswith("gs://"):
        rest = text[5:]
        bucket, _, path = rest.partition("/")
        if path:
            return GcsRef(bucket=bucket, path=path)
    if text.startswith("/api/std/assets/gcs-file?"):
        query = parse_qs(urlparse(text).query)
        path = (query.get("path") or [""])[0]
        bucket = (query.get("bucket") or [""])[0]
        if path:
            return GcsRef(bucket=bucket or DEFAULT_BUCKET, path=unquote(path))
    return None


def _gcs_ref_from_asset(asset: dict[str, Any]) -> GcsRef | None:
    bucket = str(asset.get("gcs_bucket") or asset.get("bucket") or asset.get("storage_bucket") or "").strip()
    path = str(asset.get("gcs_path") or asset.get("object_path") or asset.get("storage_path") or "").strip()
    if path:
        return GcsRef(bucket=bucket or DEFAULT_BUCKET, path=path)
    return _gcs_ref_from_url(str(asset.get("media_url") or asset.get("url") or ""))


def _scene_media_ref(scene: dict[str, Any]) -> tuple[str, GcsRef | None]:
    metadata = scene.get("metadata") if isinstance(scene.get("metadata"), dict) else {}
    for key in ("ae_effect_asset", "ae_motion_asset", "video_asset", "cowork_video_asset"):
        asset = metadata.get(key) if isinstance(metadata.get(key), dict) else {}
        ref = _gcs_ref_from_asset(asset)
        if ref:
            return key, ref
    for key in ("video_url", "ae_video_url", "ae_motion_video_url", "image_url"):
        ref = _gcs_ref_from_url(str(scene.get(key) or ""))
        if ref:
            return key, ref
    asset = metadata.get("cowork_image_asset") if isinstance(metadata.get("cowork_image_asset"), dict) else {}
    ref = _gcs_ref_from_asset(asset)
    if ref:
        return "cowork_image_asset", ref
    return "", None


def fetch_candidate_projects(limit: int = DEFAULT_PROJECT_LIMIT) -> list[dict[str, Any]]:
    base_url, headers = _supabase()
    params = {
        "select": "id,title,status,submitted_at,project_payload,progress_payload,updated_at",
        "submitted_at": "not.is.null",
        "order": "updated_at.desc",
        "limit": str(max(1, min(int(limit), 100))),
    }
    rows = _request("GET", f"{base_url}/rest/v1/std_projects", headers, params=params).json()
    return rows if isinstance(rows, list) else []


def _package_status(payload: dict[str, Any], progress: dict[str, Any]) -> str:
    render_settings = payload.get("render_settings") if isinstance(payload.get("render_settings"), dict) else {}
    meta = render_settings.get("premiere_final_asset") if isinstance(render_settings.get("premiere_final_asset"), dict) else {}
    if meta.get("status"):
        return str(meta.get("status"))
    progress_meta = progress.get("premiere_final_asset") if isinstance(progress.get("premiere_final_asset"), dict) else {}
    return str(progress_meta.get("status") or "")


def _job_from_row(row: dict[str, Any], force: bool = False) -> ProjectJob | None:
    payload = _json_object(row.get("project_payload"))
    progress = _json_object(row.get("progress_payload"))
    if not force and _package_status(payload, progress) in {"package_ready", "rendering", "ready"}:
        return None
    structure = _json_object(payload.get("structure") or row.get("pregenerated_structure"))
    scenes = structure.get("scenes")
    if not isinstance(scenes, list) or not scenes:
        return None
    if not any(_scene_media_ref(scene)[1] for scene in scenes if isinstance(scene, dict)):
        return None
    return ProjectJob(
        project_id=str(row.get("id") or ""),
        title=str(row.get("title") or payload.get("title") or payload.get("generated_title") or row.get("id") or ""),
        row=row,
        payload=payload,
        structure=structure,
    )


def find_project_jobs(rows: list[dict[str, Any]], force: bool = False) -> list[ProjectJob]:
    jobs = []
    for row in rows:
        job = _job_from_row(row, force=force)
        if job:
            jobs.append(job)
    return jobs


def _seconds(value: Any, fallback: float) -> float:
    try:
        parsed = float(value)
        return parsed if parsed > 0 else fallback
    except (TypeError, ValueError):
        return fallback


def _local_asset_path(workdir: Path, scene_number: int, ref: GcsRef) -> Path:
    suffix = Path(ref.path).suffix.lower()
    if suffix not in {".png", ".jpg", ".jpeg", ".mp4", ".mov", ".m4v", ".wav", ".mp3", ".m4a"}:
        suffix = ".mp4" if "/ae/" in ref.path or "/video" in ref.path else ".png"
    return workdir / "assets" / f"scene-{scene_number:03d}{suffix}"


def _format_srt_time(seconds: float) -> str:
    ms_total = max(0, round(seconds * 1000))
    hours, rem = divmod(ms_total, 3600_000)
    minutes, rem = divmod(rem, 60_000)
    secs, millis = divmod(rem, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


def _write_srt(scenes: list[dict[str, Any]], path: Path) -> None:
    cursor = 0.0
    lines: list[str] = []
    index = 1
    for scene in scenes:
        duration = _seconds(scene.get("duration_seconds") or scene.get("target_duration"), 5.0)
        text = str(scene.get("subtitle_text") or scene.get("scene_text") or scene.get("narration") or "").strip()
        if text:
            lines.extend([
                str(index),
                f"{_format_srt_time(cursor)} --> {_format_srt_time(cursor + duration)}",
                text.replace("\r", " ").replace("\n", " "),
                "",
            ])
            index += 1
        cursor += duration
    path.write_text("\n".join(lines), encoding="utf-8")


def _write_fcpxml(clips: list[dict[str, Any]], path: Path) -> None:
    fps = DEFAULT_FPS
    frame_duration = f"1/{fps}s"
    resources = []
    spine = []
    for idx, clip in enumerate(clips, start=1):
        asset_id = f"r{idx}"
        duration_frames = max(1, round(float(clip["duration_seconds"]) * fps))
        duration = f"{duration_frames}/{fps}s"
        resources.append(
            f'<asset id="{asset_id}" name="{escape(clip["name"])}" src="file:///{escape(str(clip["path"]).replace(os.sep, "/"))}" duration="{duration}" />'
        )
        spine.append(f'<asset-clip name="{escape(clip["name"])}" ref="{asset_id}" offset="{clip["offset_frames"]}/{fps}s" duration="{duration}" />')
    xml = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<fcpxml version="1.8">\n'
        '  <resources>\n'
        f'    <format id="fmt1" name="AIR Studio 1080p" frameDuration="{frame_duration}" width="{DEFAULT_WIDTH}" height="{DEFAULT_HEIGHT}" colorSpace="1-1-1 (Rec. 709)" />\n'
        + "\n".join(f"    {item}" for item in resources)
        + '\n  </resources>\n'
        '  <library>\n'
        '    <event name="AIR Studio Final Assembly">\n'
        '      <project name="AIR Studio Premiere Final">\n'
        f'        <sequence format="fmt1" tcStart="0s" tcFormat="NDF">\n'
        '          <spine>\n'
        + "\n".join(f"            {item}" for item in spine)
        + '\n          </spine>\n'
        '        </sequence>\n'
        '      </project>\n'
        '    </event>\n'
        '  </library>\n'
        '</fcpxml>\n'
    )
    path.write_text(xml, encoding="utf-8")


def _write_jsx_bridge(manifest_path: Path, fcpxml_path: Path, srt_path: Path, output_path: Path) -> None:
    manifest_js = str(manifest_path).replace("\\", "/")
    fcpxml_js = str(fcpxml_path).replace("\\", "/")
    srt_js = str(srt_path).replace("\\", "/")
    jsx = f"""// Premiere Pro bridge script generated by AIR Studio.
// Modern hosts should prefer the UXP bridge. This ExtendScript bridge is kept
// for legacy/manual import paths and leaves export to the operator or AME bridge.
var manifestFile = new File("{manifest_js}");
var timelineFile = new File("{fcpxml_js}");
var subtitleFile = new File("{srt_js}");
$.writeln("AIR Studio Premiere package: " + manifestFile.fsName);
$.writeln("Import timeline: " + timelineFile.fsName);
$.writeln("Import subtitles: " + subtitleFile.fsName);
if (app && app.project && timelineFile.exists) {{
  try {{
    app.project.importFiles([timelineFile.fsName], true, app.project.rootItem, false);
  }} catch (err) {{
    $.writeln("Import failed: " + err);
  }}
}}
"""
    output_path.write_text(jsx, encoding="utf-8")


def _manifest_upload_dir(project_id: str) -> str:
    return f"projects/{project_id}/premiere/final-package"


def _update_project(job: ProjectJob, asset: dict[str, Any]) -> None:
    base_url, headers = _supabase()
    payload = dict(job.payload)
    render_settings = payload.get("render_settings") if isinstance(payload.get("render_settings"), dict) else {}
    render_settings = {**render_settings, "premiere_final_asset": asset}
    payload["render_settings"] = render_settings
    progress = _json_object(job.row.get("progress_payload"))
    progress["premiere_final_asset"] = asset
    _request(
        "PATCH",
        f"{base_url}/rest/v1/std_projects?id=eq.{quote(job.project_id, safe='')}",
        {**headers, "Content-Type": "application/json", "Prefer": "return=minimal"},
        json={"project_payload": payload, "progress_payload": progress},
    )


def _job_summary(job: ProjectJob) -> dict[str, Any]:
    return {
        "job_id": f"premiere-final-{job.project_id}",
        "job_type": "premiere_final_package",
        "project_id": job.project_id,
        "project_name": job.title,
    }


def process_job(job: ProjectJob, *, keep_workdir: bool = False, open_premiere: bool = False) -> dict[str, Any]:
    workdir = PACKAGE_ROOT / f"{_safe_name(job.project_id)}-{uuid.uuid4().hex[:8]}"
    package_dir = workdir / "package"
    package_dir.mkdir(parents=True, exist_ok=True)
    scenes = [scene for scene in job.structure.get("scenes", []) if isinstance(scene, dict)]
    clips: list[dict[str, Any]] = []
    cursor_frames = 0
    write_state("downloading", 10, _job_summary(job))
    for index, scene in enumerate(scenes, start=1):
        scene_number = int(scene.get("scene_number") or scene.get("scene_order") or index)
        source_kind, ref = _scene_media_ref(scene)
        if not ref:
            continue
        local_path = _local_asset_path(workdir, scene_number, ref)
        _download_gcs_file(ref, local_path)
        duration = _seconds(scene.get("duration_seconds") or scene.get("target_duration"), 5.0)
        clips.append({
            "scene_number": scene_number,
            "name": f"scene-{scene_number:03d}-{source_kind or 'media'}",
            "source_kind": source_kind,
            "path": local_path.resolve(),
            "duration_seconds": duration,
            "offset_frames": cursor_frames,
            "gcs": {"bucket": ref.bucket, "path": ref.path},
        })
        cursor_frames += max(1, round(duration * DEFAULT_FPS))
    if not clips:
        raise PremiereWorkerError("project has no downloadable scene media")

    write_state("packaging", 45, _job_summary(job))
    fcpxml_path = package_dir / "air-premiere-final.fcpxml"
    srt_path = package_dir / "air-subtitles.srt"
    manifest_path = package_dir / "air-premiere-manifest.json"
    jsx_path = package_dir / "air-premiere-bridge.jsx"
    _write_fcpxml(clips, fcpxml_path)
    _write_srt(scenes, srt_path)
    manifest = {
        "schema": "air_studio_premiere_final/v1",
        "created_at": _now(),
        "project_id": job.project_id,
        "title": job.title,
        "fps": DEFAULT_FPS,
        "width": DEFAULT_WIDTH,
        "height": DEFAULT_HEIGHT,
        "duration_seconds": round(sum(float(clip["duration_seconds"]) for clip in clips), 3),
        "clips": [
            {**clip, "path": str(clip["path"])}
            for clip in clips
        ],
        "files": {
            "fcpxml": str(fcpxml_path.resolve()),
            "srt": str(srt_path.resolve()),
            "jsx_bridge": str(jsx_path.resolve()),
        },
        "adobe_capability": capability_report(),
        "export_strategy": "premiere_uxp_or_ame_bridge",
        "status": "package_ready",
    }
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    _write_jsx_bridge(manifest_path, fcpxml_path, srt_path, jsx_path)

    write_state("uploading", 75, _job_summary(job))
    upload_prefix = _manifest_upload_dir(job.project_id)
    uploaded: dict[str, Any] = {}
    for key, path in {"manifest": manifest_path, "fcpxml": fcpxml_path, "srt": srt_path, "jsx_bridge": jsx_path}.items():
        mime_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        bucket, gcs_path, media_url = _upload_gcs_file(path, f"{upload_prefix}/{path.name}", mime_type)
        uploaded[key] = {"bucket": bucket, "gcs_path": gcs_path, "media_url": media_url}
    asset = {
        "status": "package_ready",
        "worker": os.getenv("PREMIERE_FINAL_WORKER_ID") or worker_config.WORKER_INSTANCE_ID,
        "updated_at": _now(),
        "local_workdir": str(workdir) if keep_workdir else "",
        "manifest": uploaded["manifest"],
        "fcpxml": uploaded["fcpxml"],
        "srt": uploaded["srt"],
        "jsx_bridge": uploaded["jsx_bridge"],
        "adobe_capability": capability_report(),
        "export_strategy": "premiere_uxp_or_ame_bridge",
        "clip_count": len(clips),
    }
    _update_project(job, asset)

    if open_premiere:
        premiere = find_premiere()
        if premiere and premiere.is_file():
            subprocess.Popen([str(premiere), str(fcpxml_path)], cwd=str(premiere.parent))
    if not keep_workdir:
        # Keep the uploaded manifest as the durable handoff; local source assets
        # can be re-downloaded from their GCS refs.
        import shutil
        shutil.rmtree(workdir, ignore_errors=True)
    write_state("idle", 0, None)
    state = json.loads(STATE_FILE.read_text(encoding="utf-8"))
    state["last_success_at"] = time.time()
    STATE_FILE.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")
    return asset


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Prepare Premiere Pro final assembly packages for submitted projects.")
    parser.add_argument("--loop", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--project-id", default="")
    parser.add_argument("--project-limit", type=int, default=DEFAULT_PROJECT_LIMIT)
    parser.add_argument("--keep-workdir", action="store_true")
    parser.add_argument("--open-premiere", action="store_true")
    args = parser.parse_args(argv)

    clear_shutdown_flag(WORKER_NAME)
    write_state("starting")
    while True:
        try:
            rows = fetch_candidate_projects(args.project_limit)
            if args.project_id:
                rows = [row for row in rows if str(row.get("id")) == str(args.project_id)]
            jobs = find_project_jobs(rows, force=args.force)
            if args.dry_run:
                print(json.dumps({
                    "capability": capability_report(),
                    "candidate_count": len(jobs),
                    "jobs": [_job_summary(job) for job in jobs],
                }, ensure_ascii=False, indent=2))
                write_state("idle")
                return
            if jobs:
                process_job(jobs[0], keep_workdir=args.keep_workdir, open_premiere=args.open_premiere)
            else:
                write_state("idle")
            if not args.loop:
                return
        except Exception as exc:
            write_state("failed" if not args.loop else "idle", last_error=str(exc))
            if not args.loop:
                raise
        if not args.loop or is_shutdown_requested(WORKER_NAME):
            break
        deadline = time.time() + DEFAULT_POLL_SECONDS
        while time.time() < deadline and not is_shutdown_requested(WORKER_NAME):
            write_state("idle")
            time.sleep(min(5, max(0.5, deadline - time.time())))
    write_state("stopped")
    clear_shutdown_flag(WORKER_NAME)


if __name__ == "__main__":
    main()
