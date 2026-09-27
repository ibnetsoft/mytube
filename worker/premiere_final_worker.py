"""Premiere final assembly package worker for submitted user projects.

This worker packages submitted project media for Premiere Pro, writes an
importable FCP7 XML timeline, and exports the assembled MP4 through Adobe
Media Encoder when narration is available.
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
import zipfile
from dataclasses import dataclass
from datetime import datetime, timezone
from xml.etree import ElementTree as ET
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, quote, unquote, urlparse

import requests

import worker_config
from adobe_tools import capability_report, find_media_encoder, find_premiere
from ame_export_bridge import export as export_with_ame
from media_checkpoint import Checkpoint, fingerprint, valid_file, valid_mp4, verified_local_mp4
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
MAX_ATTEMPTS = int(os.getenv("PREMIERE_FINAL_MAX_ATTEMPTS", "3"))


class PremiereWorkerError(RuntimeError):
    pass


@dataclass(frozen=True)
class GcsRef:
    bucket: str
    path: str


@dataclass(frozen=True)
class LocalRef:
    path: str
    bytes: int
    mtime_ns: int


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


def _gcs_upload_session_path(file_path: Path, bucket: str, object_path: str) -> Path:
    import hashlib

    key = hashlib.sha256(f"{bucket}/{object_path}".encode("utf-8")).hexdigest()[:16]
    return file_path.with_name(f".{file_path.name}.{key}.gcs-upload.json")


class GcsTransientUploadError(PremiereWorkerError):
    """GCS upload failed after retryable network or server errors."""


def _gcs_valid_session_url(value: str) -> bool:
    try:
        parsed = urlparse(value)
    except ValueError:
        return False
    return parsed.scheme == "https" and parsed.hostname in {"storage.googleapis.com", "www.googleapis.com"}


def _gcs_upload_headers(creds: Any) -> dict[str, str]:
    if getattr(creds, "expired", False):
        from google.auth.transport.requests import Request

        creds.refresh(Request())
    return {"Authorization": f"Bearer {creds.token}"}


def _gcs_uploaded_bytes(response: requests.Response, size: int) -> int:
    header = response.headers.get("Range", "")
    if not header:
        return 0
    match = re.fullmatch(r"bytes=0-(\d+)", header.strip())
    if not match:
        raise PremiereWorkerError(f"GCS resumable upload returned invalid Range: {header[:100]}")
    offset = int(match.group(1)) + 1
    if offset > size:
        raise PremiereWorkerError("GCS resumable upload reported more bytes than the local file")
    return offset


def _gcs_verify_uploaded_object(response: requests.Response, bucket: str, object_path: str, size: int) -> None:
    try:
        metadata = response.json()
    except (ValueError, AttributeError):
        return
    if not isinstance(metadata, dict):
        return
    if metadata.get("bucket") and metadata["bucket"] != bucket:
        raise PremiereWorkerError("GCS upload returned a different bucket")
    if metadata.get("name") and metadata["name"] != object_path:
        raise PremiereWorkerError("GCS upload returned a different object path")
    if metadata.get("size") is not None:
        try:
            uploaded_size = int(metadata["size"])
        except (TypeError, ValueError) as exc:
            raise PremiereWorkerError("GCS upload returned invalid object size") from exc
        if uploaded_size != size:
            raise PremiereWorkerError("GCS upload returned an unexpected object size")


def _upload_gcs_file(file_path: Path, object_path: str, mime_type: str) -> tuple[str, str, str]:
    """Upload in resumable chunks, keeping the session across worker restarts."""
    creds, bucket = _gcs_credentials()
    clean_path = str(object_path or "").strip().replace("\\", "/").lstrip("/")
    if not clean_path:
        raise PremiereWorkerError("GCS object path is empty")
    stat = file_path.stat()
    size = stat.st_size
    if size <= 0:
        raise PremiereWorkerError(f"Cannot upload an empty file: {file_path}")
    session_path = _gcs_upload_session_path(file_path, bucket, clean_path)
    identity = {"bucket": bucket, "path": clean_path, "size": size, "mtime_ns": stat.st_mtime_ns}
    session_url = ""
    try:
        saved = json.loads(session_path.read_text(encoding="utf-8"))
        if all(saved.get(key) == value for key, value in identity.items()):
            candidate = str(saved.get("session_url") or "")
            if _gcs_valid_session_url(candidate):
                session_url = candidate
    except (OSError, ValueError, TypeError, AttributeError):
        pass

    def save_session(url: str) -> None:
        temporary = session_path.with_name(session_path.name + ".tmp")
        temporary.write_text(json.dumps({**identity, "session_url": url}), encoding="utf-8")
        os.replace(temporary, session_path)

    def finish(response: requests.Response) -> tuple[str, str, str]:
        _gcs_verify_uploaded_object(response, bucket, clean_path, size)
        session_path.unlink(missing_ok=True)
        return bucket, clean_path, (
            f"/api/std/assets/gcs-file?bucket={quote(bucket, safe='')}&path={quote(clean_path, safe='')}"
        )

    retryable = {408, 429, 500, 502, 503, 504}
    max_failures = 5
    failures = 0
    session_restarts = 0
    offset = 0
    check_status = bool(session_url)
    chunk_size = 8 * 1024 * 1024  # GCS requires multiples of 256 KiB, except the last chunk.

    with file_path.open("rb") as handle:
        while True:
            if not session_url:
                response = None
                try:
                    response = requests.post(
                        f"https://storage.googleapis.com/upload/storage/v1/b/{quote(bucket, safe='')}/o"
                        f"?uploadType=resumable&name={quote(clean_path, safe='')}",
                        headers={
                            **_gcs_upload_headers(creds),
                            "Content-Type": "application/json; charset=UTF-8",
                            "X-Upload-Content-Type": mime_type,
                            "X-Upload-Content-Length": str(size),
                        },
                        data=b"{}",
                        timeout=(15, 90),
                    )
                except requests.RequestException as exc:
                    failure = str(exc)
                else:
                    if response.status_code in (200, 201):
                        candidate = response.headers.get("Location", "")
                        if not _gcs_valid_session_url(candidate):
                            raise PremiereWorkerError("GCS did not return a valid resumable upload URL")
                        session_url = candidate
                        save_session(session_url)
                        offset = 0
                        failures = 0
                        check_status = False
                        continue
                    failure = f"HTTP {response.status_code}: {response.text[:300]}"
                    if response.status_code not in retryable:
                        raise PremiereWorkerError(f"GCS upload session failed: {failure}")
                failures += 1
                if failures >= max_failures:
                    raise GcsTransientUploadError(f"GCS upload session failed after {failures} attempts: {failure}")
                time.sleep(min(2 ** (failures - 1), 16))
                continue

            response = None
            try:
                if check_status:
                    response = requests.put(
                        session_url,
                        headers={
                            **_gcs_upload_headers(creds),
                            "Content-Length": "0",
                            "Content-Range": f"bytes */{size}",
                        },
                        data=b"",
                        timeout=(15, 90),
                    )
                else:
                    handle.seek(offset)
                    chunk = handle.read(min(chunk_size, size - offset))
                    if not chunk:
                        raise PremiereWorkerError("GCS upload ended before the local file was fully read")
                    response = requests.put(
                        session_url,
                        headers={
                            **_gcs_upload_headers(creds),
                            "Content-Type": mime_type,
                            "Content-Length": str(len(chunk)),
                            "Content-Range": f"bytes {offset}-{offset + len(chunk) - 1}/{size}",
                        },
                        data=chunk,
                        timeout=(15, 180),
                    )
            except requests.RequestException as exc:
                failure = str(exc)
                response = None
            if response is None or response.status_code in retryable:
                if response is not None:
                    failure = f"HTTP {response.status_code}: {response.text[:300]}"
                failures += 1
                if failures >= max_failures:
                    raise GcsTransientUploadError(f"GCS resumable upload failed after {failures} attempts: {failure}")
                check_status = True
                time.sleep(min(2 ** (failures - 1), 16))
                continue
            if response.status_code in (200, 201):
                return finish(response)
            if response.status_code in (404, 410):
                session_restarts += 1
                if session_restarts > 2:
                    raise PremiereWorkerError("GCS resumable upload session expired repeatedly")
                session_path.unlink(missing_ok=True)
                session_url = ""
                offset = 0
                check_status = False
                failures = 0
                continue
            if response.status_code != 308:
                raise PremiereWorkerError(f"GCS resumable upload failed ({response.status_code}): {response.text[:300]}")
            uploaded = _gcs_uploaded_bytes(response, size)
            if uploaded == size:
                failures += 1
                if failures >= max_failures:
                    raise GcsTransientUploadError("GCS received all bytes but did not finalize the object")
                check_status = True
                time.sleep(min(2 ** (failures - 1), 16))
                continue
            if check_status:
                # The server's Range is authoritative after a timeout or restart.
                if uploaded != offset:
                    offset = uploaded
                    failures = 0
                check_status = False
                continue
            if uploaded > offset:
                offset = uploaded
                failures = 0
                continue
            failures += 1
            if failures >= max_failures:
                raise GcsTransientUploadError("GCS resumable upload made no progress")
            check_status = True
            time.sleep(min(2 ** (failures - 1), 16))


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


def _local_ref_from_asset(asset: dict[str, Any]) -> LocalRef | None:
    if asset.get("storage_provider") != "local" or asset.get("status") != "ready":
        return None
    duration = _seconds(asset.get("duration_seconds"), 1.0)
    path = verified_local_mp4(asset.get("local_path"), worker_config.TEMP_DIR / "ae_highlight",
                              max(0.5, duration * 0.8))
    if path:
        try:
            if asset.get("local_bytes") and path.stat().st_size != int(asset["local_bytes"]):
                return None
            if asset.get("local_mtime_ns") and path.stat().st_mtime_ns != int(asset["local_mtime_ns"]):
                return None
        except (TypeError, ValueError):
            return None
        return LocalRef(str(path), path.stat().st_size, path.stat().st_mtime_ns)
    return None


def _scene_media_ref(scene: dict[str, Any]) -> tuple[str, GcsRef | LocalRef | None]:
    metadata = scene.get("metadata") if isinstance(scene.get("metadata"), dict) else {}
    for key in ("ae_effect_asset", "ae_motion_asset", "video_asset", "cowork_video_asset"):
        asset = metadata.get(key) if isinstance(metadata.get(key), dict) else {}
        local_ref = _local_ref_from_asset(asset)
        if local_ref:
            return key, local_ref
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


def _project_audio_ref(payload: dict[str, Any]) -> GcsRef | None:
    for key in ("audio_asset", "tts_asset", "narration_asset"):
        asset = payload.get(key)
        if isinstance(asset, dict):
            ref = _gcs_ref_from_asset(asset)
            if ref:
                return ref
    for key in ("audio_url", "tts_url"):
        ref = _gcs_ref_from_url(str(payload.get(key) or ""))
        if ref:
            return ref
    return None


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
    package_status = _package_status(payload, progress)
    asset = (payload.get("render_settings") or {}).get("premiere_final_asset") if isinstance(payload.get("render_settings"), dict) else {}
    if not force and package_status in {"package_ready", "ready", "needs_attention"}:
        return None
    if not force and package_status == "retry_wait" and isinstance(asset, dict) and float(asset.get("next_retry_at") or 0) > time.time():
        return None
    structure = _json_object(payload.get("structure") or row.get("pregenerated_structure"))
    scenes = structure.get("scenes")
    if not isinstance(scenes, list) or not scenes:
        return None
    # An approved longform project must not be assembled from stills while
    # its scene AE jobs are still rendering or waiting for retry.
    for scene in scenes:
        if not isinstance(scene, dict):
            continue
        planned = (scene.get("ae_effect_plan") if isinstance(scene.get("ae_effect_plan"), dict) and scene["ae_effect_plan"].get("enabled")
                   else scene.get("ae_motion_plan") if isinstance(scene.get("ae_motion_plan"), dict) and scene["ae_motion_plan"].get("enabled")
                   else None)
        if planned:
            kind = "effect" if isinstance(scene.get("ae_effect_plan"), dict) and scene["ae_effect_plan"].get("enabled") else "motion"
            meta = scene.get("metadata") if isinstance(scene.get("metadata"), dict) else {}
            asset = meta.get(f"ae_{kind}_asset") if isinstance(meta.get(f"ae_{kind}_asset"), dict) else {}
            # A local MP4 may already exist while visual review is pending.
            # It must not enter the final timeline until that review is approved.
            if asset.get("status") and asset.get("status") != "ready":
                return None
            if asset.get("storage_provider") == "local":
                if not _local_ref_from_asset(asset):
                    return None
            elif not (_gcs_ref_from_asset(asset) or _gcs_ref_from_url(str(scene.get(
                    "ae_video_url" if kind == "effect" else "ae_motion_video_url") or ""))):
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


def _local_asset_path(workdir: Path, scene_number: int, ref: GcsRef | LocalRef) -> Path:
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


def _write_premiere_xml(clips: list[dict[str, Any]], path: Path, audio_path: Path | None = None) -> None:
    """Write Final Cut Pro 7 XML (xmeml), the interchange Premiere imports."""
    root = ET.Element("xmeml", version="4")
    sequence = ET.SubElement(root, "sequence", id="air-studio-final")
    ET.SubElement(sequence, "name").text = "AIR Studio Final"
    duration_frames = max(int(clip["offset_frames"]) + max(1, round(float(clip["duration_seconds"]) * DEFAULT_FPS)) for clip in clips)
    ET.SubElement(sequence, "duration").text = str(duration_frames)
    rate = ET.SubElement(sequence, "rate")
    ET.SubElement(rate, "timebase").text = str(DEFAULT_FPS)
    ET.SubElement(rate, "ntsc").text = "FALSE"
    media = ET.SubElement(sequence, "media")
    video = ET.SubElement(media, "video")
    sample = ET.SubElement(video, "format")
    sample = ET.SubElement(sample, "samplecharacteristics")
    ET.SubElement(sample, "width").text = str(DEFAULT_WIDTH)
    ET.SubElement(sample, "height").text = str(DEFAULT_HEIGHT)
    ET.SubElement(sample, "anamorphic").text = "FALSE"
    ET.SubElement(sample, "pixelaspectratio").text = "square"
    track = ET.SubElement(video, "track")
    for index, clip in enumerate(clips, 1):
        frames = max(1, round(float(clip["duration_seconds"]) * DEFAULT_FPS))
        start = int(clip["offset_frames"])
        item = ET.SubElement(track, "clipitem", id=f"air-clip-{index}")
        for key, value in (("name", clip["name"]), ("duration", frames), ("start", start),
                           ("end", start + frames), ("in", 0), ("out", frames)):
            ET.SubElement(item, key).text = str(value)
        file_element = ET.SubElement(item, "file", id=f"air-file-{index}")
        ET.SubElement(file_element, "name").text = Path(clip["path"]).name
        ET.SubElement(file_element, "pathurl").text = Path(clip["path"]).resolve().as_uri()
        file_rate = ET.SubElement(file_element, "rate")
        ET.SubElement(file_rate, "timebase").text = str(DEFAULT_FPS)
        ET.SubElement(file_rate, "ntsc").text = "FALSE"
    if audio_path:
        audio = ET.SubElement(media, "audio")
        audio_track = ET.SubElement(audio, "track")
        audio_item = ET.SubElement(audio_track, "clipitem", id="air-narration")
        for key, value in (("name", audio_path.name), ("duration", duration_frames),
                           ("start", 0), ("end", duration_frames), ("in", 0), ("out", duration_frames)):
            ET.SubElement(audio_item, key).text = str(value)
        audio_file = ET.SubElement(audio_item, "file", id="air-narration-file")
        ET.SubElement(audio_file, "name").text = audio_path.name
        ET.SubElement(audio_file, "pathurl").text = audio_path.resolve().as_uri()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b'<?xml version="1.0" encoding="utf-8"?>\n<!DOCTYPE xmeml>\n' + ET.tostring(root, encoding="utf-8"))


def _write_jsx_bridge(manifest_path: Path, timeline_path: Path, srt_path: Path, output_path: Path) -> None:
    manifest_js = str(manifest_path).replace("\\", "/")
    fcpxml_js = str(timeline_path).replace("\\", "/")
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


def _export_preset() -> Path:
    configured = os.getenv("PREMIERE_EXPORT_PRESET")
    if configured:
        preset = Path(configured)
    else:
        encoder = find_media_encoder()
        if not encoder:
            raise PremiereWorkerError("Adobe Media Encoder executable was not found")
        preset = encoder.parent / "MediaIO" / "systempresets" / "4E49434B_48323634" / "High Quality 1080 HD.epr"
    if not preset.is_file():
        raise PremiereWorkerError(f"H.264 export preset not found: {preset}")
    return preset


def _write_relink_script(path: Path) -> None:
    path.write_text('''"""Run after extracting this archive to regenerate local Premiere media paths."""
from pathlib import Path
from urllib.parse import unquote, urlparse
from xml.etree import ElementTree as ET

root = Path(__file__).resolve().parent
xml_path = root / "package" / "air-premiere-final.xml"
tree = ET.parse(xml_path)
for file_node in tree.findall(".//file"):
    url_node = file_node.find("pathurl")
    if url_node is None or not url_node.text:
        continue
    name = Path(unquote(urlparse(url_node.text).path)).name
    matches = list((root / "assets").glob(name))
    if len(matches) != 1:
        raise RuntimeError(f"Missing or ambiguous media file: {name}")
    url_node.text = matches[0].resolve().as_uri()
tree.write(xml_path, encoding="utf-8", xml_declaration=True)
print(f"Relinked: {xml_path}")
''', encoding="utf-8")


def _manifest_upload_dir(project_id: str) -> str:
    return f"projects/{project_id}/premiere/final-package"


def _ffmpeg_executable() -> str:
    configured = os.getenv("FFMPEG_PATH") or shutil.which("ffmpeg")
    if configured:
        return configured
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception as exc:
        raise PremiereWorkerError("FFmpeg is required for final MP4 export") from exc


def _render_final_mp4(clips: list[dict[str, Any]], audio_path: Path | None, srt_path: Path, output: Path) -> None:
    ffmpeg = _ffmpeg_executable()
    segments: list[Path] = []
    for index, clip in enumerate(clips, 1):
        source = Path(clip["path"])
        duration = float(clip["duration_seconds"])
        segment = output.parent / f"segment-{index:03d}.mp4"
        command = [ffmpeg, "-y"]
        if source.suffix.lower() in {".png", ".jpg", ".jpeg"}:
            command += ["-loop", "1", "-framerate", str(DEFAULT_FPS)]
        else:
            command += ["-stream_loop", "-1"]
        command += ["-i", str(source), "-t", f"{duration:.3f}",
                    "-vf", f"scale={DEFAULT_WIDTH}:{DEFAULT_HEIGHT}:force_original_aspect_ratio=decrease,pad={DEFAULT_WIDTH}:{DEFAULT_HEIGHT}:(ow-iw)/2:(oh-ih)/2,fps={DEFAULT_FPS},format=yuv420p",
                    "-an", "-c:v", "libx264", "-preset", "medium", "-crf", "20", str(segment)]
        result = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=900)
        if result.returncode or not segment.is_file():
            raise PremiereWorkerError(f"FFmpeg scene {index} failed: {result.stderr[-800:]}")
        segments.append(segment)
    concat_file = output.parent / "segments.txt"
    concat_file.write_text("".join(f"file '{path.as_posix()}'\n" for path in segments), encoding="utf-8")
    joined = output.parent / "joined.mp4"
    result = subprocess.run([ffmpeg, "-y", "-f", "concat", "-safe", "0", "-i", str(concat_file), "-c", "copy", str(joined)], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=900)
    if result.returncode or not joined.is_file():
        raise PremiereWorkerError(f"FFmpeg concat failed: {result.stderr[-800:]}")
    command = [ffmpeg, "-y", "-i", str(joined)]
    if audio_path:
        command += ["-i", str(audio_path)]
    else:
        command += ["-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=48000"]
    has_subtitles = srt_path.stat().st_size > 0
    if has_subtitles:
        command += ["-i", str(srt_path)]
    command += ["-map", "0:v:0"]
    command += ["-map", "1:a:0", "-c:a", "aac", "-ar", "48000", "-ac", "2", "-b:a", "192k", "-af", "apad"]
    if has_subtitles:
        command += ["-map", "2:s:0", "-c:s", "mov_text"]
    command += ["-c:v", "copy", "-t", f"{sum(float(c['duration_seconds']) for c in clips):.3f}", "-movflags", "+faststart", str(output)]
    result = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=900)
    if result.returncode or not output.is_file() or output.stat().st_size < 1024:
        raise PremiereWorkerError(f"FFmpeg final export failed: {result.stderr[-800:]}")


def _attach_subtitles(adobe_mp4: Path, srt_path: Path, final_path: Path) -> None:
    if not srt_path.is_file() or srt_path.stat().st_size == 0:
        shutil.copy2(adobe_mp4, final_path)
        return
    command = [_ffmpeg_executable(), "-y", "-i", str(adobe_mp4), "-i", str(srt_path),
               "-map", "0", "-map", "1:s:0", "-c:v", "copy", "-c:a", "copy",
               "-c:s", "mov_text", "-movflags", "+faststart", str(final_path)]
    result = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=900)
    if result.returncode or not final_path.is_file() or final_path.stat().st_size < 1024:
        raise PremiereWorkerError(f"Subtitle mux failed: {result.stderr[-800:]}")


def _update_project(job: ProjectJob, asset: dict[str, Any]) -> None:
    base_url, headers = _supabase()
    settings = job.payload.get("render_settings") if isinstance(job.payload.get("render_settings"), dict) else {}
    previous = settings.get("premiere_final_asset") if isinstance(settings.get("premiere_final_asset"), dict) else {}
    # A row-locked RPC merges only this asset into the latest JSON. Rewriting
    # the poll-time project_payload here would erase AE scenes committed since
    # this final package started rendering.
    result = _request(
        "POST",
        f"{base_url}/rest/v1/rpc/air_update_premiere_final_asset",
        {**headers, "Content-Type": "application/json"},
        json={"p_project_id": job.project_id, "p_asset": asset,
              "p_expected_status": str(previous.get("status") or ""),
              "p_expected_updated_at": str(previous.get("updated_at") or "")},
    ).json()
    if not isinstance(result, dict) or result.get("applied") is not True:
        code = result.get("code") if isinstance(result, dict) else "invalid_response"
        raise PremiereWorkerError(f"Premiere final asset update was not applied: {code}")


def _record_project_failure(job: ProjectJob, error: Exception) -> None:
    settings = job.payload.get("render_settings") if isinstance(job.payload.get("render_settings"), dict) else {}
    previous = settings.get("premiere_final_asset") if isinstance(settings.get("premiere_final_asset"), dict) else {}
    attempts = int(previous.get("attempts") or 0) + 1
    # A temporary GCS outage should not strand an otherwise finished video
    # after the usual three render attempts. Its resumable session is retained.
    limit = int(os.getenv("PREMIERE_FINAL_UPLOAD_MAX_ATTEMPTS", "48")) if isinstance(error, GcsTransientUploadError) else MAX_ATTEMPTS
    status = "needs_attention" if attempts >= limit else "retry_wait"
    _update_project(job, {"status": status, "attempts": attempts,
                          "next_retry_at": time.time() + min(1800, 30 * (2 ** min(attempts - 1, 6))) if status == "retry_wait" else 0,
                          "error": str(error)[:800], "updated_at": _now()})


def _job_summary(job: ProjectJob) -> dict[str, Any]:
    return {
        "job_id": f"premiere-final-{job.project_id}",
        "job_type": "premiere_final_package",
        "project_id": job.project_id,
        "project_name": job.title,
    }


def process_job(job: ProjectJob, *, keep_workdir: bool = False, open_premiere: bool = False) -> dict[str, Any]:
    scenes = [scene for scene in job.structure.get("scenes", []) if isinstance(scene, dict)]
    audio_ref = _project_audio_ref(job.payload)
    export_backend = (os.getenv("PREMIERE_FINAL_BACKEND") or "adobe").lower()
    fingerprint_scenes = []
    for scene in scenes:
        _kind, ref = _scene_media_ref(scene)
        fingerprint_scenes.append({
            "number": scene.get("scene_number") or scene.get("scene_order"),
            "media": ref.__dict__ if ref else None,
            "duration": scene.get("duration_seconds") or scene.get("target_duration"),
            "subtitle": scene.get("subtitle_text") or scene.get("scene_text") or scene.get("narration"),
        })
    identity = fingerprint({"version": 2, "project": job.project_id, "backend": export_backend,
                            "title": job.title,
                            "fps": DEFAULT_FPS, "width": DEFAULT_WIDTH, "height": DEFAULT_HEIGHT,
                            "audio": audio_ref.__dict__ if audio_ref else None, "scenes": fingerprint_scenes})
    workdir = PACKAGE_ROOT / f"{_safe_name(job.project_id)}-{identity}"
    checkpoint = Checkpoint(workdir / "checkpoint.json", identity)
    package_dir = workdir / "package"
    package_dir.mkdir(parents=True, exist_ok=True)
    clips: list[dict[str, Any]] = []
    cursor_frames = 0
    write_state("downloading", 10, _job_summary(job))
    for index, scene in enumerate(scenes, start=1):
        scene_number = int(scene.get("scene_number") or scene.get("scene_order") or index)
        source_kind, ref = _scene_media_ref(scene)
        if not ref:
            raise PremiereWorkerError(f"scene {scene_number} has no downloadable media")
        local_path = _local_asset_path(workdir, scene_number, ref)
        duration = _seconds(scene.get("duration_seconds") or scene.get("target_duration"), 5.0)
        video_source = local_path.suffix.lower() in {".mp4", ".mov", ".m4v"}
        scene_meta = scene.get("metadata") if isinstance(scene.get("metadata"), dict) else {}
        source_meta = scene_meta.get(source_kind) if isinstance(scene_meta.get(source_kind), dict) else {}
        media_min_seconds = max(0.5, _seconds(source_meta.get("duration_seconds"), 0.5) * 0.8)
        local_valid = valid_mp4(local_path, media_min_seconds) if video_source else valid_file(local_path)
        if isinstance(ref, LocalRef) and local_valid:
            local_valid = (local_path.stat().st_size == ref.bytes and
                           local_path.stat().st_mtime_ns == ref.mtime_ns)
        if not local_valid:
            if isinstance(ref, LocalRef):
                source = verified_local_mp4(ref.path, worker_config.TEMP_DIR / "ae_highlight",
                                            media_min_seconds)
                if not source:
                    raise PremiereWorkerError(f"scene {scene_number} local AE MP4 is missing or invalid")
                local_path.parent.mkdir(parents=True, exist_ok=True)
                temporary = local_path.with_name(local_path.name + ".copying")
                shutil.copy2(source, temporary)
                os.replace(temporary, local_path)
            else:
                _download_gcs_file(ref, local_path)
        if not (valid_mp4(local_path, media_min_seconds) if video_source else valid_file(local_path)):
            raise PremiereWorkerError(f"scene {scene_number} media is incomplete or invalid")
        clips.append({
            "scene_number": scene_number,
            "name": f"scene-{scene_number:03d}-{source_kind or 'media'}",
            "source_kind": source_kind,
            "path": local_path.resolve(),
            "duration_seconds": duration,
            "offset_frames": cursor_frames,
            "gcs": {"bucket": ref.bucket, "path": ref.path} if isinstance(ref, GcsRef) else None,
            "local_source": ref.path if isinstance(ref, LocalRef) else None,
        })
        cursor_frames += max(1, round(duration * DEFAULT_FPS))
    if not clips:
        raise PremiereWorkerError("project has no downloadable scene media")

    audio_path = None
    if audio_ref:
        suffix = Path(audio_ref.path).suffix.lower()
        if suffix not in {".wav", ".mp3", ".m4a", ".aac"}:
            suffix = ".wav"
        audio_path = workdir / "assets" / f"narration{suffix}"
        if not valid_file(audio_path):
            _download_gcs_file(audio_ref, audio_path)
    checkpoint.mark("downloaded", {"clips": len(clips), "narration": bool(audio_path)})

    write_state("packaging", 45, _job_summary(job))
    timeline_path = package_dir / "air-premiere-final.xml"
    srt_path = package_dir / "air-subtitles.srt"
    manifest_path = package_dir / "air-premiere-manifest.json"
    jsx_path = package_dir / "air-premiere-bridge.jsx"
    relink_path = workdir / "relink.py"
    _write_premiere_xml(clips, timeline_path, audio_path)
    _write_srt(scenes, srt_path)
    manifest = {
        "schema": "air_studio_premiere_final/v1",
        "created_at": checkpoint.get("created_at") or _now(),
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
        "narration": {"path": str(audio_path), "bucket": audio_ref.bucket, "gcs_path": audio_ref.path} if audio_path and audio_ref else None,
        "files": {
            "premiere_xml": str(timeline_path.resolve()),
            "srt": str(srt_path.resolve()),
            "jsx_bridge": str(jsx_path.resolve()),
        },
        "adobe_capability": capability_report(),
        "export_strategy": "manual_premiere_export_pending_bridge",
        "status": "package_ready",
    }
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    _write_jsx_bridge(manifest_path, timeline_path, srt_path, jsx_path)
    _write_relink_script(relink_path)

    final_path = package_dir / "air-final.mp4"
    expected_seconds = sum(float(clip["duration_seconds"]) for clip in clips)
    required_seconds = max(0.5, expected_seconds * 0.9)
    write_state("rendering", 60, _job_summary(job))
    if valid_mp4(final_path, required_seconds):
        if export_backend == "adobe":
            manifest["files"]["adobe_export"] = str((package_dir / "air-adobe-export.mp4").resolve())
    elif export_backend == "adobe":
        adobe_path = package_dir / "air-adobe-export.mp4"
        intermediate_path = package_dir / "air-assembly.mp4"
        empty_srt = package_dir / "air-no-subtitles.srt"
        empty_srt.write_text("", encoding="utf-8")
        if not valid_mp4(intermediate_path, required_seconds):
            _render_final_mp4(clips, audio_path, empty_srt, intermediate_path)
        checkpoint.mark("assembled", {"path": str(intermediate_path), "bytes": intermediate_path.stat().st_size})
        status_path = package_dir / "air-adobe-status.txt"
        export_jsx = package_dir / "air-adobe-export.jsx"
        if not valid_mp4(adobe_path, required_seconds):
            rendered = export_with_ame(intermediate_path, _export_preset(), package_dir / "ame-output",
                                       status_path, export_jsx,
                                       timeout_seconds=int(os.getenv("PREMIERE_EXPORT_TIMEOUT_SECONDS", "3600")))
            shutil.copy2(rendered, adobe_path)
        checkpoint.mark("adobe_exported", {"path": str(adobe_path), "bytes": adobe_path.stat().st_size})
        _attach_subtitles(adobe_path, srt_path, final_path)
        manifest["files"]["adobe_export"] = str(adobe_path.resolve())
    elif export_backend == "ffmpeg":
        _render_final_mp4(clips, audio_path, srt_path, final_path)
    else:
        raise PremiereWorkerError(f"Unknown PREMIERE_FINAL_BACKEND: {export_backend}")
    if not valid_mp4(final_path, required_seconds):
        raise PremiereWorkerError("Final MP4 is missing or shorter than the planned timeline")
    manifest["status"] = "ready"
    manifest["export_strategy"] = "adobe_media_encoder" if export_backend == "adobe" else "ffmpeg_from_premiere_package"
    manifest["files"]["final_video"] = str(final_path.resolve())
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    checkpoint.mark("rendered", {"path": str(final_path), "bytes": final_path.stat().st_size})
    checkpoint.mark("created_at", manifest["created_at"])

    archive_path = package_dir / "air-premiere-package.zip"
    archived = checkpoint.get("archive_ready")
    if not (isinstance(archived, dict) and valid_file(archive_path) and
            archived.get("bytes") == archive_path.stat().st_size):
        building = archive_path.with_name(archive_path.name + ".building")
        with zipfile.ZipFile(building, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
            for file_path in [timeline_path, srt_path, manifest_path, jsx_path, relink_path, *(clip["path"] for clip in clips), *([audio_path] if audio_path else [])]:
                archive.write(file_path, file_path.relative_to(workdir))
        os.replace(building, archive_path)
        checkpoint.mark("archive_ready", {"bytes": archive_path.stat().st_size})

    write_state("uploading", 75, _job_summary(job))
    upload_prefix = _manifest_upload_dir(job.project_id)
    uploaded: dict[str, Any] = {}
    for key, path in {"manifest": manifest_path, "premiere_xml": timeline_path, "srt": srt_path, "jsx_bridge": jsx_path, "archive": archive_path}.items():
        saved = checkpoint.get("uploaded_" + key)
        if isinstance(saved, dict) and saved.get("gcs_path"):
            uploaded[key] = saved
            continue
        mime_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        bucket, gcs_path, media_url = _upload_gcs_file(path, f"{upload_prefix}/{path.name}", mime_type)
        uploaded[key] = {"bucket": bucket, "gcs_path": gcs_path, "media_url": media_url}
        checkpoint.mark("uploaded_" + key, uploaded[key])
    if final_path.is_file():
        saved = checkpoint.get("uploaded_final_video")
        final_stat = final_path.stat()
        final_object_path = f"projects/{job.project_id}/premiere/final/air-final.mp4"
        if (isinstance(saved, dict) and saved.get("gcs_path") == final_object_path and
                saved.get("source_bytes") == final_stat.st_size and
                saved.get("source_mtime_ns") == final_stat.st_mtime_ns):
            uploaded["final_video"] = saved
        else:
            bucket, gcs_path, media_url = _upload_gcs_file(final_path, final_object_path, "video/mp4")
            uploaded["final_video"] = {"bucket": bucket, "gcs_path": gcs_path, "media_url": media_url,
                                       "source_bytes": final_stat.st_size, "source_mtime_ns": final_stat.st_mtime_ns}
            checkpoint.mark("uploaded_final_video", uploaded["final_video"])
    asset = {
        "status": "ready" if "final_video" in uploaded else "package_ready",
        "worker": os.getenv("PREMIERE_FINAL_WORKER_ID") or worker_config.WORKER_INSTANCE_ID,
        "updated_at": _now(),
        "local_workdir": str(workdir) if keep_workdir else "",
        "manifest": uploaded["manifest"],
        "premiere_xml": uploaded["premiere_xml"],
        "srt": uploaded["srt"],
        "jsx_bridge": uploaded["jsx_bridge"],
        "archive": uploaded["archive"],
        "final_video": uploaded.get("final_video"),
        "adobe_capability": capability_report(),
        "export_strategy": manifest["export_strategy"],
        "clip_count": len(clips),
    }
    _update_project(job, asset)
    checkpoint.mark("committed", {"status": asset["status"], "updated_at": asset["updated_at"]})

    if open_premiere:
        premiere = find_premiere()
        if premiere and premiere.is_file():
            subprocess.Popen([str(premiere), str(timeline_path)], cwd=str(premiere.parent))
    # The XML references these local files. Keep them until a Premiere/AME
    # bridge has imported and exported the sequence or a later cleanup job
    # verifies the final artifact. Deleting them here breaks every clip.
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
                try:
                    process_job(jobs[0], keep_workdir=args.keep_workdir, open_premiere=args.open_premiere)
                except Exception as job_error:
                    _record_project_failure(jobs[0], job_error)
                    raise
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
