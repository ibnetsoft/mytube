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
        "topic": project.get("topic"),
        "duration_seconds": settings.get("duration_seconds"),
    }


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

    return {"status": "ok", "plan": plan, "config": music_config}


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

    return {
        "status": "ok",
        "file_path": f"/output/{req.project_id}/assets/audio/longform_music/tracks/{filename}",
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
    image: UploadFile = File(...),
    track_files: List[str] = Form(...),
    track_durations: List[int] = Form(default=None),
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

    output_dir = os.path.join(config.OUTPUT_DIR, str(project_id), "assets", "video")
    os.makedirs(output_dir, exist_ok=True)

    image_path = os.path.join(output_dir, f"temp_image_{int(time.time())}.jpg")
    try:
        content = await image.read()
        with open(image_path, "wb") as f:
            f.write(content)
    except Exception as e:
        raise HTTPException(400, f"Failed to save image: {e}")

    concat_txt = os.path.join(output_dir, f"concat_{int(time.time())}.txt")
    try:
        with open(concat_txt, "w") as f:
            for tf in track_files:
                audio_file = tf.replace("/output/", config.OUTPUT_DIR + "/")
                if os.path.exists(audio_file):
                    f.write(f"file '{os.path.abspath(audio_file)}'\n")

        combined_audio = os.path.join(output_dir, f"combined_{int(time.time())}.mp3")
        result = subprocess.run(
            ["ffmpeg", "-f", "concat", "-safe", "0", "-i", concat_txt, "-c", "copy", combined_audio],
            capture_output=True,
            timeout=600,
        )
        if result.returncode != 0:
            raise Exception(f"ffmpeg concat failed: {result.stderr.decode()}")
    except Exception as e:
        raise HTTPException(500, f"Audio combine failed: {e}")
    finally:
        if os.path.exists(concat_txt):
            os.remove(concat_txt)

    video_file = os.path.join(output_dir, f"playlist_{int(time.time())}.mp4")
    try:
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
    except Exception as e:
        raise HTTPException(500, f"Video render failed: {e}")
    finally:
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
