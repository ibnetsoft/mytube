"""Generate standard longform scenes 13-18 with the local ComfyUI instance."""
from __future__ import annotations

import argparse
import json
import os
import random
import shutil
import subprocess
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote

import requests

import worker_config
from shutdown_flag import clear_shutdown_flag, is_shutdown_requested


DEFAULT_COMFY_URL = os.getenv("COMFYUI_SERVER_URL", "http://127.0.0.1:8188").rstrip("/")
DEFAULT_BUCKET = os.getenv("GCS_BUCKET_NAME") or "air-studio-prod"
STATE_FILE = worker_config.STATE_DIR / "comfy_scene_video_worker.json"
STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
SCENE_START = 13
SCENE_END = 18
SCENE_SECONDS = 5
VIDEO_FPS = 24
VIDEO_FRAMES = VIDEO_FPS * SCENE_SECONDS + 1
VIDEO_WIDTH = 832
VIDEO_HEIGHT = 480
NEGATIVE_PROMPT = (
    "subtitles, captions, text, letters, logos, watermarks, speech bubbles, "
    "dialogue, narration, music, sound effects, audio, flicker, scene cuts, "
    "identity change, deformed face, extra fingers, extra limbs, low quality"
)


class ComfySceneError(RuntimeError):
    pass


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _write_state(status: str, *, project_id: str = "", scene_number: int = 0, error: str = "") -> None:
    STATE_FILE.write_text(json.dumps({
        "pid": os.getpid(), "status": status,
        "current_job": {"project_id": project_id, "scene_number": scene_number} if project_id else None,
        "heartbeat_at": time.time(), "last_error": error[:800],
    }, ensure_ascii=False), encoding="utf-8")


def _supabase() -> tuple[str, dict[str, str]]:
    url = (os.getenv("NEXT_PUBLIC_SUPABASE_URL") or os.getenv("SUPABASE_URL") or "").rstrip("/")
    key = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or ""
    if not url or not key:
        raise ComfySceneError("Supabase service credentials are required")
    return url, {"apikey": key, "Authorization": f"Bearer {key}"}


def _request(method: str, url: str, headers: dict[str, str], **kwargs: Any) -> requests.Response:
    response = requests.request(method, url, headers=headers, timeout=60, **kwargs)
    if not response.ok:
        raise ComfySceneError(f"HTTP {response.status_code} {url}: {response.text[:400]}")
    return response


def _gcs_credentials():
    email = os.getenv("GCS_CLIENT_EMAIL") or os.getenv("GOOGLE_CLIENT_EMAIL") or ""
    private_key = os.getenv("GCS_PRIVATE_KEY") or os.getenv("GOOGLE_PRIVATE_KEY") or ""
    project_id = os.getenv("GCS_PROJECT_ID") or os.getenv("GOOGLE_CLOUD_PROJECT") or "air-studio-prod"
    bucket = os.getenv("GCS_BUCKET_NAME") or DEFAULT_BUCKET
    if not (email and private_key and bucket):
        raise ComfySceneError("GCS credentials are required to register ComfyUI videos")
    from google.oauth2 import service_account
    from google.auth.transport.requests import Request
    credentials = service_account.Credentials.from_service_account_info({
        "type": "service_account", "project_id": project_id,
        "private_key": private_key.replace("\\n", "\n"), "client_email": email,
        "token_uri": "https://oauth2.googleapis.com/token",
    }, scopes=["https://www.googleapis.com/auth/devstorage.read_write"])
    credentials.refresh(Request())
    return credentials, bucket


def _download_gcs(bucket: str, object_path: str, target: Path) -> None:
    credentials, default_bucket = _gcs_credentials()
    bucket = bucket or default_bucket
    response = requests.get(
        f"https://storage.googleapis.com/storage/v1/b/{quote(bucket, safe='')}/o/{quote(object_path, safe='')}?alt=media",
        headers={"Authorization": f"Bearer {credentials.token}"}, timeout=300,
    )
    if not response.ok:
        raise ComfySceneError(f"GCS source image download failed ({response.status_code})")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(response.content)


def _upload_gcs(source: Path, object_path: str) -> tuple[str, str]:
    credentials, bucket = _gcs_credentials()
    with source.open("rb") as handle:
        response = requests.post(
            f"https://storage.googleapis.com/upload/storage/v1/b/{quote(bucket, safe='')}/o?uploadType=media&name={quote(object_path, safe='')}",
            headers={"Authorization": f"Bearer {credentials.token}", "Content-Type": "video/mp4"},
            data=handle, timeout=900,
        )
    if response.status_code not in (200, 201):
        raise ComfySceneError(f"GCS video upload failed ({response.status_code}): {response.text[:300]}")
    return bucket, object_path


def _upscale_video(source: Path, target: Path) -> Path:
    """Resize Wan's 832x480 output to the project's 1080p landscape master."""
    try:
        import imageio_ffmpeg
        ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        ffmpeg = os.getenv("FFMPEG_PATH") or shutil.which("ffmpeg")
    if not ffmpeg:
        raise ComfySceneError("FFmpeg is required to upscale the ComfyUI clip to 1080p")
    target.parent.mkdir(parents=True, exist_ok=True)
    command = [str(ffmpeg), "-y", "-i", str(source), "-vf", "scale=1920:1080:flags=lanczos",
               "-an", "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-pix_fmt", "yuv420p", str(target)]
    result = subprocess.run(command, capture_output=True, text=True, timeout=600)
    if result.returncode or not target.is_file() or target.stat().st_size < 20_000:
        raise ComfySceneError(f"1080p clip resize failed: {(result.stderr or result.stdout)[-800:]}")
    return target


def build_wan22_i2v_prompt(image_name: str, prompt: str, prefix: str, seed: int | None = None) -> dict[str, Any]:
    """Create a small API-format graph using the installed Wan 2.2 GGUF models."""
    return {
        "1": {"class_type": "UnetLoaderGGUF", "inputs": {"unet_name": os.getenv("COMFYUI_WAN_MODEL", "Wan2.2-TI2V-5B-Q4_K_M.gguf")}},
        "2": {"class_type": "CLIPLoaderGGUF", "inputs": {"clip_name": os.getenv("COMFYUI_WAN_TEXT_ENCODER", "umt5-xxl-encoder-Q3_K_S.gguf"), "type": "wan"}},
        "3": {"class_type": "VAELoader", "inputs": {"vae_name": os.getenv("COMFYUI_WAN_VAE", "wan2.2_vae.safetensors")}},
        "4": {"class_type": "CLIPTextEncode", "inputs": {"text": prompt, "clip": ["2", 0]}},
        "5": {"class_type": "CLIPTextEncode", "inputs": {"text": NEGATIVE_PROMPT, "clip": ["2", 0]}},
        "6": {"class_type": "ModelSamplingSD3", "inputs": {"model": ["1", 0], "shift": 5.0}},
        "7": {"class_type": "LoadImage", "inputs": {"image": image_name}},
        "8": {"class_type": "Wan22ImageToVideoLatent", "inputs": {
            "vae": ["3", 0], "start_image": ["7", 0], "width": VIDEO_WIDTH,
            "height": VIDEO_HEIGHT, "length": VIDEO_FRAMES, "batch_size": 1,
        }},
        "9": {"class_type": "KSampler", "inputs": {
            "model": ["6", 0], "seed": int(seed if seed is not None else random.randrange(0, 2**32)),
            "steps": int(os.getenv("COMFYUI_WAN_STEPS", "8")),
            "cfg": float(os.getenv("COMFYUI_WAN_CFG", "4.0")), "sampler_name": "euler",
            "scheduler": "simple", "positive": ["4", 0], "negative": ["5", 0],
            "latent_image": ["8", 0], "denoise": 1.0,
        }},
        "10": {"class_type": "VAEDecode", "inputs": {"samples": ["9", 0], "vae": ["3", 0]}},
        "11": {"class_type": "CreateVideo", "inputs": {"images": ["10", 0], "fps": VIDEO_FPS}},
        # ComfyUI 0.37 exposes this dynamic combo as its selected key plus
        # sibling live inputs in API-format prompts.
        "12": {"class_type": "SaveVideo", "inputs": {
            "video": ["11", 0], "filename_prefix": prefix,
            "format": "mp4", "codec": "h264",
        }},
    }


def _scene_source(assets: list[dict[str, Any]], scene_number: int) -> tuple[str, str] | None:
    for asset in assets:
        if int(asset.get("scene_number") or 0) != scene_number or asset.get("asset_type") != "image":
            continue
        if asset.get("status") not in {"uploaded", "assigned"}:
            continue
        metadata = asset.get("metadata") if isinstance(asset.get("metadata"), dict) else {}
        path = str(metadata.get("gcs_path") or metadata.get("storage_path") or "").strip().lstrip("/")
        bucket = str(metadata.get("gcs_bucket") or metadata.get("storage_bucket") or "").strip()
        if path:
            return bucket, path
    return None


def _scene_list(project: dict[str, Any]) -> list[dict[str, Any]]:
    payload = project.get("project_payload") if isinstance(project.get("project_payload"), dict) else {}
    structure = payload.get("structure") if isinstance(payload.get("structure"), dict) else {}
    scenes = structure.get("scenes") if isinstance(structure.get("scenes"), list) else payload.get("scenes")
    return scenes if isinstance(scenes, list) else []


def _comfy_upload_image(base_url: str, image_path: Path, subfolder: str) -> str:
    with image_path.open("rb") as handle:
        response = requests.post(
            f"{base_url}/upload/image",
            files={"image": (image_path.name, handle, "image/png")},
            data={"type": "input", "subfolder": subfolder, "overwrite": "true"}, timeout=180,
        )
    if not response.ok:
        raise ComfySceneError(f"ComfyUI image upload failed ({response.status_code}): {response.text[:300]}")
    body = response.json()
    return f"{body.get('subfolder', '')}/{body['name']}".lstrip("/")


def _run_comfy_prompt(base_url: str, graph: dict[str, Any], timeout_seconds: int) -> Path:
    response = requests.post(f"{base_url}/prompt", json={"prompt": graph, "client_id": str(uuid.uuid4())}, timeout=60)
    if not response.ok:
        raise ComfySceneError(f"ComfyUI rejected workflow ({response.status_code}): {response.text[:1200]}")
    prompt_id = str(response.json().get("prompt_id") or "")
    if not prompt_id:
        raise ComfySceneError("ComfyUI returned no prompt_id")
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        time.sleep(5)
        history_response = requests.get(f"{base_url}/history/{prompt_id}", timeout=30)
        if not history_response.ok:
            continue
        history = history_response.json().get(prompt_id) or {}
        status = history.get("status") or {}
        if status.get("status_str") == "error" or status.get("completed") is False and status.get("messages"):
            raise ComfySceneError(f"ComfyUI generation failed: {json.dumps(status, ensure_ascii=False)[:1000]}")
        outputs = history.get("outputs") or {}
        saved = outputs.get("12", {})
        # SaveVideo moved from `videos` to `images` in newer ComfyUI versions.
        videos = saved.get("videos") or saved.get("images") or []
        if not videos:
            continue
        item = videos[0]
        view = requests.get(f"{base_url}/view", params={
            "filename": item.get("filename"), "subfolder": item.get("subfolder", ""),
            "type": item.get("type", "output"),
        }, timeout=300)
        if not view.ok:
            raise ComfySceneError(f"ComfyUI output download failed ({view.status_code})")
        output = worker_config.TEMP_DIR / "comfy_scene_video" / f"{prompt_id}.mp4"
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(view.content)
        if not output.is_file() or output.stat().st_size < 20_000:
            raise ComfySceneError("ComfyUI returned an empty or truncated video")
        return output
    raise ComfySceneError(f"ComfyUI generation timed out after {timeout_seconds}s (prompt {prompt_id})")


def _register_video(project: dict[str, Any], scene: dict[str, Any], scene_row: dict[str, Any] | None,
                    scene_number: int, gcs_bucket: str, gcs_path: str, file_path: Path) -> None:
    base_url, headers = _supabase()
    project_id = str(project["id"])
    scene_id = scene_row.get("id") if scene_row else None
    timestamp = _now()
    asset_metadata = {
        "storage_provider": "gcs", "storage_bucket": gcs_bucket, "storage_path": gcs_path,
        "gcs_bucket": gcs_bucket, "gcs_path": gcs_path,
        "storage_public_url": f"/api/std/assets/gcs-file?bucket={quote(gcs_bucket, safe='')}&path={quote(gcs_path, safe='')}",
        "upload_mode": "local_comfyui_wan22_i2v", "generator": "ComfyUI Wan 2.2 TI2V 5B",
        "duration_seconds": SCENE_SECONDS, "fps": VIDEO_FPS, "width": VIDEO_WIDTH, "height": VIDEO_HEIGHT,
        "video_prompt": str(scene.get("video_prompt") or "")[:20000],
    }
    asset_row = {
        "project_id": project_id, "scene_id": scene_id, "scene_number": scene_number,
        "asset_type": "video", "drive_file_id": None, "drive_folder_id": None,
        "file_name": f"scene_{scene_number:03d}_comfyui.mp4", "mime_type": "video/mp4",
        "file_size": file_path.stat().st_size, "status": "assigned", "uploaded_by": None,
        "metadata": asset_metadata,
    }
    asset_response = _request("POST", f"{base_url}/rest/v1/std_project_assets", {**headers, "Content-Type": "application/json", "Prefer": "return=representation"}, json=asset_row)
    inserted = asset_response.json()
    asset_id = str(inserted[0].get("id") or "") if isinstance(inserted, list) and inserted else ""

    if scene_row:
        metadata = scene_row.get("metadata") if isinstance(scene_row.get("metadata"), dict) else {}
        generation = {"status": "ready", "worker": worker_config.WORKER_INSTANCE_ID, "updated_at": timestamp,
                     "duration_seconds": SCENE_SECONDS, "fps": VIDEO_FPS, "gcs_bucket": gcs_bucket, "gcs_path": gcs_path}
        video_metadata = {
            "visual_type": "video", "video_prompt_required": True,
            "video_generation_mode": "comfyui", "comfyui_video_generation": generation,
            "video_gcs_bucket": gcs_bucket, "video_gcs_path": gcs_path,
            "video_asset_id": asset_id,
            "comfyui_video_asset": {"gcs_bucket": gcs_bucket, "gcs_path": gcs_path, "asset_id": asset_id},
        }
        _request("PATCH", f"{base_url}/rest/v1/std_project_scenes?id=eq.{scene_id}",
                 {**headers, "Content-Type": "application/json"},
                 json={"asset_status": "ready", "metadata": {**metadata, **video_metadata}, "updated_at": timestamp})

    # Keep a worker-readable GCS reference on project_payload too; the AE worker
    # polls this payload after submission and uses the original clip as footage.
    payload = project.get("project_payload") if isinstance(project.get("project_payload"), dict) else {}
    next_payload = dict(payload)
    for key in ("scenes",):
        rows = payload.get(key)
        if isinstance(rows, list):
            next_payload[key] = [_patch_scene_payload(row, scene_number, asset_id, gcs_bucket, gcs_path) for row in rows]
    structure = payload.get("structure") if isinstance(payload.get("structure"), dict) else {}
    if isinstance(structure.get("scenes"), list):
        next_payload["structure"] = {**structure, "scenes": [
            _patch_scene_payload(row, scene_number, asset_id, gcs_bucket, gcs_path)
            for row in structure["scenes"]
        ]}
    query = f"id=eq.{project_id}"
    if project.get("updated_at"):
        query += f"&updated_at=eq.{quote(str(project['updated_at']), safe=':.-+') }"
    _request("PATCH", f"{base_url}/rest/v1/std_projects?{query}",
             {**headers, "Content-Type": "application/json", "Prefer": "return=minimal"},
             json={"project_payload": next_payload, "updated_at": timestamp})


def _patch_scene_payload(scene: Any, scene_number: int, asset_id: str, bucket: str, path: str) -> Any:
    if not isinstance(scene, dict):
        return scene
    try:
        number = int(scene.get("scene_number") or scene.get("scene_order") or 0)
    except (TypeError, ValueError):
        return scene
    if number != scene_number:
        return scene
    metadata = scene.get("metadata") if isinstance(scene.get("metadata"), dict) else {}
    # Keep the preplanned AE post-process plan intact and explicitly identify
    # the registered ComfyUI MP4 as its source. The AE poller will only claim
    # this scene after this source path appears.
    motion_plan = scene.get("ae_motion_plan") if isinstance(scene.get("ae_motion_plan"), dict) else {}
    if motion_plan.get("enabled"):
        motion_plan = {
            **motion_plan,
            "input_source": "comfyui_video_asset",
            "postprocess_after": "comfyui_video_ready",
        }
    image_url = str(scene.get("image_url") or "").strip()
    if not image_url and scene.get("image_generation_mode") == "comfyui":
        # During the standard project handoff the approved first-frame image is
        # attached as a std_project_assets row, then copied onto the scene.
        # Preserve its AE fallback path for reference, but do not fabricate one.
        image_url = str(metadata.get("image_url") or "").strip()
    return {
        **scene, "video_url": f"/api/std/assets/gcs-file?bucket={quote(bucket, safe='')}&path={quote(path, safe='')}",
        "visual_type": "video", "video_prompt_required": True, "video_generation_mode": "comfyui",
        **({"ae_motion_plan": motion_plan} if motion_plan else {}),
        "metadata": {**metadata, "visual_type": "video", "video_prompt_required": True,
                     "video_generation_mode": "comfyui", "video_gcs_bucket": bucket,
                     "video_gcs_path": path, "video_asset_id": asset_id,
                     "comfyui_video_asset": {"gcs_bucket": bucket, "gcs_path": path, "asset_id": asset_id}},
    }


def process_one() -> bool:
    base_url, headers = _supabase()
    comfy_url = DEFAULT_COMFY_URL
    projects_response = _request("GET", f"{base_url}/rest/v1/std_projects", headers, params={
        "select": "id,title,status,submitted_at,updated_at,project_payload", "status": "in.(claimed,in_progress)",
        "submitted_at": "is.null", "order": "updated_at.asc", "limit": "30",
    })
    projects = projects_response.json()
    for project in projects if isinstance(projects, list) else []:
        project_id = str(project.get("id") or "")
        if not project_id:
            continue
        assets_response = _request("GET", f"{base_url}/rest/v1/std_project_assets", headers, params={
            "select": "id,scene_id,scene_number,asset_type,status,file_name,mime_type,metadata",
            "project_id": f"eq.{project_id}", "status": "in.(uploaded,assigned)",
            "asset_type": "in.(image,video)", "order": "created_at.asc", "limit": "200",
        })
        assets = assets_response.json() if assets_response.ok else []
        video_numbers = {int(a.get("scene_number") or 0) for a in assets if a.get("asset_type") == "video"}
        scenes = _scene_list(project)
        scene_rows_response = _request("GET", f"{base_url}/rest/v1/std_project_scenes", headers, params={
            "select": "id,scene_number,metadata", "project_id": f"eq.{project_id}",
            "scene_number": f"gte.{SCENE_START}", "order": "scene_number.asc", "limit": "12",
        })
        scene_rows = {int(row.get("scene_number") or 0): row for row in scene_rows_response.json() or []}
        for scene in scenes:
            try:
                number = int(scene.get("scene_number") or scene.get("scene_order") or 0)
            except (TypeError, ValueError):
                continue
            if not SCENE_START <= number <= SCENE_END or number in video_numbers:
                continue
            prompt = str(scene.get("video_prompt") or "").strip()
            image_source = _scene_source(assets, number)
            if not prompt or not image_source:
                continue
            scene_row = scene_rows.get(number)
            current_meta = scene_row.get("metadata") if isinstance(scene_row, dict) and isinstance(scene_row.get("metadata"), dict) else {}
            generation_state = current_meta.get("comfyui_video_generation") if isinstance(current_meta.get("comfyui_video_generation"), dict) else {}
            if float(generation_state.get("next_retry_at") or 0) > time.time():
                continue
            if generation_state.get("status") == "generating" and time.time() - float(generation_state.get("started_at_epoch") or 0) < 3600:
                continue

            _write_state("generating", project_id=project_id, scene_number=number)
            if scene_row:
                _request("PATCH", f"{base_url}/rest/v1/std_project_scenes?id=eq.{scene_row['id']}",
                         {**headers, "Content-Type": "application/json"}, json={"metadata": {
                             **current_meta, "visual_type": "video", "video_prompt_required": True,
                             "video_generation_mode": "comfyui", "comfyui_video_generation": {
                                 "status": "generating", "started_at": _now(), "started_at_epoch": time.time(),
                                 "worker": worker_config.WORKER_INSTANCE_ID,
                             },
                         }, "updated_at": _now()})
            local_input = worker_config.TEMP_DIR / "comfy_scene_video" / f"{project_id}_{number:03d}_input.png"
            try:
                bucket, image_object = image_source
                _download_gcs(bucket, image_object, local_input)
                comfy_image = _comfy_upload_image(comfy_url, local_input, f"air_studio/{project_id}")
                object_path = f"std-projects/{project_id}/scene_{number:03d}_comfyui.mp4"
                prefix = f"air_studio/{project_id}/scene_{number:03d}_comfyui"
                graph = build_wan22_i2v_prompt(comfy_image, prompt, prefix)
                raw_video_path = _run_comfy_prompt(comfy_url, graph, int(os.getenv("COMFYUI_JOB_TIMEOUT_SECONDS", "3600")))
                video_path = _upscale_video(raw_video_path, raw_video_path.with_name(raw_video_path.stem + "_1080p.mp4"))
                gcs_bucket, gcs_path = _upload_gcs(video_path, object_path)
                _register_video(project, scene, scene_row, number, gcs_bucket, gcs_path, video_path)
                _write_state("idle")
                print(f"[ComfyUI] Ready project={project_id} scene={number} gcs={gcs_path}", flush=True)
                return True
            except Exception as exc:
                attempts = int(generation_state.get("attempts") or 0) + 1
                retry_after = 600 * attempts
                if scene_row:
                    _request("PATCH", f"{base_url}/rest/v1/std_project_scenes?id=eq.{scene_row['id']}",
                             {**headers, "Content-Type": "application/json"}, json={"metadata": {
                                 **current_meta, "visual_type": "video", "video_prompt_required": True,
                                 "video_generation_mode": "comfyui", "comfyui_video_generation": {
                                     "status": "failed", "error": str(exc)[:800], "attempts": attempts,
                                     "next_retry_at": time.time() + retry_after, "updated_at": _now(),
                                 },
                             }, "updated_at": _now()})
                _write_state("error", project_id=project_id, scene_number=number, error=str(exc))
                print(f"[ComfyUI] Deferred project={project_id} scene={number}: {exc}", file=sys.stderr, flush=True)
                return False
    _write_state("idle")
    return False


def _loop(poll_seconds: int) -> int:
    clear_shutdown_flag("comfy_scene_video_worker")
    _write_state("idle")
    print("[ComfyUI] scene video worker started", flush=True)
    while not is_shutdown_requested("comfy_scene_video_worker"):
        try:
            process_one()
        except Exception as exc:
            _write_state("error", error=str(exc))
            print(f"[ComfyUI] poll failed: {exc}", file=sys.stderr, flush=True)
        deadline = time.time() + poll_seconds
        while time.time() < deadline and not is_shutdown_requested("comfy_scene_video_worker"):
            time.sleep(min(1.0, max(0.0, deadline - time.time())))
    _write_state("stopped")
    clear_shutdown_flag("comfy_scene_video_worker")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate scenes 13-18 with local ComfyUI Wan 2.2")
    parser.add_argument("--loop", action="store_true")
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--poll-seconds", type=int, default=int(os.getenv("COMFYUI_POLL_SECONDS", "20")))
    args, _ = parser.parse_known_args()
    if "--role" in sys.argv:
        args.loop = True
    if args.loop and not args.once:
        return _loop(max(5, args.poll_seconds))
    return 0 if process_one() else 1


if __name__ == "__main__":
    raise SystemExit(main())
