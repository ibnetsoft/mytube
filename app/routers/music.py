"""음악 기획 API — 플랜 생성, 스타일/가사 제안, 트랙 미리듣기."""
import json
import os
import time
from typing import Any, Dict, List, Optional
import subprocess

from fastapi import APIRouter, HTTPException, File, Form, UploadFile
from pydantic import BaseModel, Field

import database as db
from config import config
from services.elevenlabs_music_service import elevenlabs_music_service
from services.music_plan_service import music_plan_service
from services.remote_drive_render_service import remote_drive_render_service
from services.remote_render_service import package_music_project_assets
from services.web_admin_client import web_admin_client

router = APIRouter(prefix="/api/music", tags=["Music"])


class MusicConfigPayload(BaseModel):
    project_id: int
    config: Dict[str, Any] = Field(default_factory=dict)
    force_regenerate: bool = False


class MusicSuggestStylesRequest(BaseModel):
    topic: str = ""
    genre: str = "lofi"
    language: str = "ko"


class MusicSuggestLyricsRequest(BaseModel):
    topic: str = ""
    style_prompt: str = ""
    language: str = "ko"


class MusicPreviewTrackRequest(BaseModel):
    project_id: int
    track_index: int = 0
    duration_seconds: int = 20
    prompt: Optional[str] = None
    force_instrumental: bool = True


class MusicGenerateTrackRequest(BaseModel):
    project_id: int
    track_index: int = 0
    duration_seconds: int  # Required, no default
    prompt: str  # Required
    force_instrumental: bool = True


class MusicSaveConfigRequest(BaseModel):
    project_id: int
    config: Dict[str, Any] = Field(default_factory=dict)
    duration_seconds: Optional[int] = None
    topic: Optional[str] = None


class MusicSaveTracksRequest(BaseModel):
    project_id: int
    tracks: List[Dict[str, Any]] = Field(default_factory=list)


class MusicSavePlanRequest(BaseModel):
    project_id: int
    plan: Dict[str, Any] = Field(default_factory=dict)
    config: Optional[Dict[str, Any]] = None


class MusicDeleteTrackRequest(BaseModel):
    project_id: int
    index: Optional[int] = None
    file_path: Optional[str] = None


def _load_generated_tracks(project_id: int) -> List[Dict[str, Any]]:
    settings = db.get_project_settings(project_id) or {}
    raw_tracks = settings.get("longform_music_generated_tracks_json")
    discovered_tracks = _discover_generated_tracks(project_id)
    if not raw_tracks:
        return discovered_tracks
    try:
        parsed = json.loads(raw_tracks)
        saved_tracks = parsed if isinstance(parsed, list) else []
    except Exception:
        saved_tracks = []
    return _merge_generated_tracks(saved_tracks, discovered_tracks)


def _track_merge_key(track: Dict[str, Any], fallback_index: int) -> str:
    if track.get("index") is not None:
        try:
            return f"index:{int(track.get('index'))}"
        except Exception:
            pass
    if track.get("file_path"):
        return f"path:{track.get('file_path')}"
    return f"fallback:{fallback_index}"


def _merge_generated_tracks(
    saved_tracks: List[Dict[str, Any]],
    discovered_tracks: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    merged: Dict[str, Dict[str, Any]] = {}
    order: List[str] = []

    for fallback_index, track in enumerate(saved_tracks or []):
        if not isinstance(track, dict):
            continue
        key = _track_merge_key(track, fallback_index)
        merged[key] = dict(track)
        order.append(key)

    for fallback_index, track in enumerate(discovered_tracks or []):
        if not isinstance(track, dict):
            continue
        key = _track_merge_key(track, fallback_index)
        existing = merged.get(key, {})
        combined = {**track, **existing}
        if combined.get("file_path") and combined.get("status") in (None, "", "pending", "ready"):
            combined["status"] = "done"
        merged[key] = combined
        if key not in order:
            order.append(key)

    return [merged[key] for key in order if merged.get(key)]


def _resolve_track_local_path(file_path: str) -> Optional[str]:
    if not file_path or not isinstance(file_path, str):
        return None
    normalized = file_path.replace("\\", "/")
    if not normalized.startswith("/output/"):
        return None
    relative = normalized[len("/output/"):].strip("/")
    absolute = os.path.abspath(os.path.join(config.OUTPUT_DIR, relative))
    output_root = os.path.abspath(config.OUTPUT_DIR)
    if not absolute.startswith(output_root):
        return None
    return absolute


def _discover_generated_tracks(project_id: int) -> List[Dict[str, Any]]:
    track_dir = os.path.join(config.OUTPUT_DIR, str(project_id), "assets", "audio", "longform_music", "tracks")
    if not os.path.isdir(track_dir):
        return []

    tracks_by_index: Dict[int, Dict[str, Any]] = {}
    fallback_index = 0
    filenames = sorted(
        os.listdir(track_dir),
        key=lambda name: os.path.getmtime(os.path.join(track_dir, name)),
    )
    for filename in filenames:
        if not filename.lower().endswith((".mp3", ".wav", ".m4a")):
            continue
        track_index = fallback_index
        fallback_index += 1
        parts = filename.split("_")
        if len(parts) >= 2 and parts[0] == "track":
            try:
                track_index = int(parts[1])
            except Exception:
                pass
        tracks_by_index[track_index] = {
            "title": f"Track {track_index + 1:02d}",
            "prompt": "",
            "duration_seconds": 0,
            "status": "done",
            "selected": True,
            "index": track_index,
            "file_path": f"/output/{project_id}/assets/audio/longform_music/tracks/{filename}",
        }
    return [tracks_by_index[index] for index in sorted(tracks_by_index)]


def _save_generated_tracks(project_id: int, tracks: List[Dict[str, Any]]) -> None:
    db.update_project_setting(
        project_id,
        "longform_music_generated_tracks_json",
        json.dumps(tracks or [], ensure_ascii=False),
    )


@router.get("/plan/{project_id}")
async def get_music_plan(project_id: int):
    project = db.get_project(project_id)
    if not project:
        raise HTTPException(404, "Project not found")

    settings = db.get_project_settings(project_id) or {}
    plan = music_plan_service.get_plan(project_id)
    music_config = music_plan_service.parse_music_config(settings.get("longform_music"))

    return {
        "status": "ok",
        "plan": plan,
        "config": music_config,
        "track_plans": music_plan_service.get_track_plans(project_id),
        "generated_tracks": _load_generated_tracks(project_id),
        "topic": project.get("topic"),
        "project_name": project.get("name"),
        "duration_seconds": settings.get("duration_seconds"),
    }


@router.get("/templates")
async def get_music_plan_templates():
    templates = web_admin_client.fetch_music_plan_templates()
    return {"status": "ok", "templates": templates}


@router.post("/save-config")
async def save_music_config(req: MusicSaveConfigRequest):
    project = db.get_project(req.project_id)
    if not project:
        raise HTTPException(404, "Project not found")

    music_plan_service.save_config(req.project_id, req.config)

    if req.duration_seconds is not None:
        db.update_project_setting(req.project_id, "duration_seconds", int(req.duration_seconds))
        req.config["playlist_duration_seconds"] = int(req.duration_seconds)
        music_plan_service.save_config(req.project_id, req.config)

    if req.topic is not None:
        db.update_project(req.project_id, topic=req.topic)

    return {"status": "ok"}


@router.post("/tracks")
async def save_music_tracks(req: MusicSaveTracksRequest):
    project = db.get_project(req.project_id)
    if not project:
        raise HTTPException(404, "Project not found")

    _save_generated_tracks(req.project_id, req.tracks)
    return {"status": "ok", "tracks": req.tracks}


@router.post("/plan/save")
async def save_music_plan(req: MusicSavePlanRequest):
    project = db.get_project(req.project_id)
    if not project:
        raise HTTPException(404, "Project not found")

    plan = dict(req.plan or {})
    config = dict(req.config or {})
    if config:
        music_plan_service.save_plan(req.project_id, plan, config)
    else:
        music_plan_service.save_plan(req.project_id, plan)

    playlist_title = str(plan.get("playlist_title") or "").strip()
    if playlist_title:
        db.update_project(req.project_id, topic=playlist_title)

    return {"status": "ok", "plan": plan, "track_plans": music_plan_service.get_track_plans(req.project_id)}


@router.post("/tracks/delete")
async def delete_music_track(req: MusicDeleteTrackRequest):
    project = db.get_project(req.project_id)
    if not project:
        raise HTTPException(404, "Project not found")

    saved_tracks = _load_generated_tracks(req.project_id)
    remaining_tracks: List[Dict[str, Any]] = []
    deleted = False

    for track in saved_tracks:
        if not isinstance(track, dict):
            continue
        track_index = track.get("index")
        track_path = track.get("file_path")
        index_match = req.index is not None and str(track_index) == str(req.index)
        path_match = bool(req.file_path) and track_path == req.file_path
        if index_match or path_match:
            deleted = True
            local_path = _resolve_track_local_path(track_path or req.file_path or "")
            if local_path and os.path.exists(local_path):
                try:
                    os.remove(local_path)
                except OSError:
                    pass
            continue
        remaining_tracks.append(track)

    _save_generated_tracks(req.project_id, remaining_tracks)
    return {"status": "ok", "deleted": deleted, "tracks": remaining_tracks}


@router.post("/plan")
async def create_music_plan(req: MusicConfigPayload):
    project = db.get_project(req.project_id)
    if not project:
        raise HTTPException(404, "Project not found")

    music_config = dict(req.config or {})
    settings = db.get_project_settings(req.project_id) or {}

    if not music_config.get("playlist_duration_seconds"):
        music_config["playlist_duration_seconds"] = int(
            settings.get("duration_seconds") or music_config.get("playlist_duration_seconds") or 3600
        )

    plan = await music_plan_service.generate_plan(
        req.project_id,
        music_config,
        force_regenerate=req.force_regenerate,
    )
    music_plan_service.save_plan(req.project_id, plan, music_config)

    if plan.get("playlist_title") and not project.get("topic"):
        db.update_project(req.project_id, topic=plan["playlist_title"])

    return {"status": "ok", "plan": plan, "config": music_config, "track_plans": music_plan_service.get_track_plans(req.project_id)}


@router.post("/suggest-styles")
async def suggest_music_styles(req: MusicSuggestStylesRequest):
    try:
        result = await music_plan_service.suggest_styles(req.topic, req.genre, req.language)
        return {"status": "ok", **result}
    except Exception as e:
        raise HTTPException(500, str(e))


@router.post("/suggest-lyrics")
async def suggest_music_lyrics(req: MusicSuggestLyricsRequest):
    try:
        lyrics = await music_plan_service.suggest_lyrics(req.topic, req.style_prompt, req.language)
        return {"status": "ok", "lyrics": lyrics}
    except Exception as e:
        raise HTTPException(500, str(e))


@router.get("/style-tags")
async def get_style_tags(genre: str = "lofi"):
    return {"status": "ok", "tags": music_plan_service.get_style_tags(genre)}


@router.post("/generate-track")
async def generate_music_track(req: MusicGenerateTrackRequest):
    project = db.get_project(req.project_id)
    if not project:
        raise HTTPException(404, "Project not found")

    prompt = (req.prompt or "").strip()
    if not prompt:
        raise HTTPException(400, "Track prompt is empty")

    if not config.ELEVENLABS_API_KEY:
        raise HTTPException(400, "ElevenLabs API key not configured")

    duration_ms = max(3000, int(req.duration_seconds * 1000))
    print(f"[MusicGenerate] Track {req.track_index}: duration_seconds={req.duration_seconds}, duration_ms={duration_ms}")
    try:
        audio_bytes = await elevenlabs_music_service.compose(
            prompt,
            music_length_ms=duration_ms,
            force_instrumental=req.force_instrumental,
        )
    except Exception as e:
        raise HTTPException(500, str(e))

    track_dir = os.path.join(config.OUTPUT_DIR, str(req.project_id), "assets", "audio", "longform_music", "tracks")
    os.makedirs(track_dir, exist_ok=True)
    filename = f"track_{req.track_index:02d}_{int(time.time())}.mp3"
    file_path = os.path.join(track_dir, filename)
    with open(file_path, "wb") as f:
        f.write(audio_bytes)

    web_path = f"/output/{req.project_id}/assets/audio/longform_music/tracks/{filename}"
    generated_tracks = _load_generated_tracks(req.project_id)
    track_item = {
        "title": None,
        "prompt": prompt,
        "duration_seconds": req.duration_seconds,
        "actual_duration_seconds": duration_ms / 1000,
        "status": "done",
        "selected": True,
        "index": req.track_index,
        "file_path": web_path,
    }
    matched = False
    for index, item in enumerate(generated_tracks):
        if int(item.get("index", -1)) == req.track_index:
            generated_tracks[index] = {**item, **track_item, "title": item.get("title")}
            matched = True
            break
    if not matched:
        generated_tracks.append(track_item)
    _save_generated_tracks(req.project_id, generated_tracks)

    return {
        "status": "ok",
        "file_path": web_path,
        "duration_seconds": duration_ms / 1000,
        "track_index": req.track_index,
    }


@router.post("/preview-track")
async def preview_music_track(req: MusicPreviewTrackRequest):
    project = db.get_project(req.project_id)
    if not project:
        raise HTTPException(404, "Project not found")

    prompt = (req.prompt or "").strip()
    if not prompt:
        plan = music_plan_service.get_plan(req.project_id)
        if not plan or not plan.get("tracks"):
            raise HTTPException(400, "No track plan found. Generate a plan first.")
        idx = max(0, min(req.track_index, len(plan["tracks"]) - 1))
        prompt = str(plan["tracks"][idx].get("prompt") or plan["tracks"][idx].get("title") or "").strip()
    if not prompt:
        raise HTTPException(400, "Track prompt is empty")

    if not config.ELEVENLABS_API_KEY:
        raise HTTPException(400, "ElevenLabs API key is not configured")

    duration_ms = max(3000, min(int(req.duration_seconds or 20) * 1000, 60000))
    try:
        audio_bytes = await elevenlabs_music_service.compose(
            prompt,
            music_length_ms=duration_ms,
            force_instrumental=req.force_instrumental,
        )
    except Exception as e:
        raise HTTPException(500, str(e))

    preview_dir = os.path.join(
        config.OUTPUT_DIR, str(req.project_id), "assets", "audio", "longform_music", "previews"
    )
    os.makedirs(preview_dir, exist_ok=True)
    filename = f"preview_{req.track_index}_{int(time.time())}.mp3"
    file_path = os.path.join(preview_dir, filename)
    with open(file_path, "wb") as f:
        f.write(audio_bytes)

    return {
        "status": "ok",
        "audio_url": f"/output/{req.project_id}/assets/audio/longform_music/previews/{filename}",
        "duration_seconds": duration_ms / 1000,
    }


@router.post("/render-playlist")
async def render_music_playlist(
    project_id: int = Form(...),
    playlist_title: str = Form(...),
    image: Optional[UploadFile] = File(default=None),
    track_files: List[str] = Form(...),
    track_durations: List[int] = Form(default=None),
    render_target: str = Form(default="drive_api"),
):
    project = db.get_project(project_id)
    if not project:
        raise HTTPException(404, "Project not found")

    if not track_files or not isinstance(track_files, list):
        track_files = [track_files] if isinstance(track_files, str) else []

    if track_durations is None:
        track_durations = []
    elif not isinstance(track_durations, list):
        track_durations = [track_durations] if isinstance(track_durations, str) else []

    selected_track_files = []
    for tf in track_files:
        audio_file = _resolve_track_local_path(tf)
        if audio_file and os.path.exists(audio_file):
            selected_track_files.append(tf)

    if not selected_track_files:
        raise HTTPException(400, "No valid music tracks were selected.")

    if render_target == "drive_api":
        package_path = None
        try:
            if image is not None and getattr(image, "filename", None):
                cover_dir = os.path.join(config.OUTPUT_DIR, str(project_id), "assets", "images", "longform_music")
                os.makedirs(cover_dir, exist_ok=True)
                ext = os.path.splitext(image.filename or "")[1].lower() or ".jpg"
                saved_name = f"playlist_cover_{int(time.time())}{ext}"
                saved_path = os.path.join(cover_dir, saved_name)
                content = await image.read()
                with open(saved_path, "wb") as f:
                    f.write(content)
                web_path = f"/output/{project_id}/assets/images/longform_music/{saved_name}"
                db.update_project_setting(project_id, "template_image_url", web_path)

            settings = db.get_project_settings(project_id) or {}
            if not settings.get("template_image_url") and not settings.get("background_video_url"):
                raise HTTPException(400, "Cover image or background video is required before rendering.")
            if not settings.get("thumbnail_url"):
                raise HTTPException(400, "Thumbnail image is required before final rendering.")

            metadata = db.get_project_metadata(project_id, "longform_music") or {}
            resolved_title = (
                settings.get("title")
                or (metadata.get("titles") or [None])[0]
                or playlist_title
            )
            resolved_description = metadata.get("description") or settings.get("description")
            if not resolved_title or not resolved_description:
                raise HTTPException(400, "Title and description metadata must be prepared before final rendering.")

            db.update_project(project_id, status="remote_packaging")
            package_path = package_music_project_assets(
                project_id,
                selected_track_files,
                playlist_title=playlist_title,
            )
            result = remote_drive_render_service.enqueue_packaged_project(
                project_id,
                package_path,
                metadata={
                    "playlist_title": playlist_title,
                    "track_count": len(selected_track_files),
                    "track_durations": track_durations,
                    "total_duration_seconds": sum(int(item or 0) for item in track_durations),
                    "app_mode": "longform_music",
                    "render_style": "music_playlist",
                    "queue_type": "music_playlist_final",
                    "display_type": "longform_music",
                    "job_stage": "package_uploaded",
                    "admin_publish_status": "render_pending",
                    "admin_action_required": "publish_after_render",
                    "final_asset_bundle": True,
                    "thumbnail_ready": True,
                    "metadata_ready": True,
                },
            )
            return {
                "status": "queued",
                "message": "Google Drive API 렌더 대기열에 등록되었습니다.",
                "task_id": result.get("task_id"),
                "asset_file_id": (result.get("drive_file") or {}).get("id"),
                "track_count": len(selected_track_files),
            }
        finally:
            if package_path and os.path.exists(package_path):
                try:
                    os.remove(package_path)
                except Exception:
                    pass

    output_dir = os.path.join(config.OUTPUT_DIR, str(project_id), "assets", "video")
    os.makedirs(output_dir, exist_ok=True)
    if image is None:
        raise HTTPException(400, "Image file is required for local rendering.")

    image_path = os.path.join(output_dir, f"temp_image_{int(time.time())}.jpg")
    combined_audio = os.path.join(output_dir, f"combined_{int(time.time())}.mp3")
    concat_txt = os.path.join(output_dir, f"concat_{int(time.time())}.txt")
    try:
        content = await image.read()
        with open(image_path, "wb") as f:
            f.write(content)

        with open(concat_txt, "w", encoding="utf-8") as f:
            for tf in selected_track_files:
                audio_file = _resolve_track_local_path(tf)
                if audio_file and os.path.exists(audio_file):
                    f.write(f"file '{os.path.abspath(audio_file)}'\n")

        result = subprocess.run(
            ["ffmpeg", "-f", "concat", "-safe", "0", "-i", concat_txt, "-c", "copy", combined_audio],
            capture_output=True,
            timeout=600,
        )
        if result.returncode != 0:
            raise Exception(f"ffmpeg concat failed: {result.stderr.decode()}")

        video_file = os.path.join(output_dir, f"playlist_{int(time.time())}.mp4")
        result = subprocess.run(
            [
                "ffmpeg",
                "-loop", "1",
                "-i", image_path,
                "-i", combined_audio,
                "-c:v", "libx264",
                "-c:a", "aac",
                "-pix_fmt", "yuv420p",
                "-shortest",
                "-y",
                video_file,
            ],
            capture_output=True,
            timeout=600,
        )
        if result.returncode != 0:
            raise Exception(f"ffmpeg render failed: {result.stderr.decode()}")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"Video render failed: {e}")
    finally:
        if os.path.exists(concat_txt):
            os.remove(concat_txt)
        if os.path.exists(image_path):
            os.remove(image_path)
        if os.path.exists(combined_audio):
            os.remove(combined_audio)

    total_duration = sum(d for d in track_durations if isinstance(d, (int, float)))
    return {
        "status": "ok",
        "video_url": f"/output/{project_id}/assets/video/playlist_{int(time.time())}.mp4",
        "playlist_title": playlist_title,
        "track_count": len(track_files),
        "total_duration_seconds": total_duration,
    }
