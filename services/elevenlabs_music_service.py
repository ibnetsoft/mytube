import json
import os
import time
from typing import Any, Dict, List, Optional

import httpx

from config import config


class ElevenLabsMusicService:
    """Small REST wrapper for ElevenLabs Music API."""

    BASE_URL = "https://api.elevenlabs.io/v1/music"

    def __init__(self):
        self.api_key = config.ELEVENLABS_API_KEY

    def _headers(self) -> Dict[str, str]:
        api_key = config.ELEVENLABS_API_KEY or self.api_key
        if not api_key:
            raise RuntimeError("ElevenLabs API key is missing")
        return {
            "xi-api-key": api_key,
            "Content-Type": "application/json",
        }

    async def compose(
        self,
        prompt: str,
        *,
        music_length_ms: int = 30000,
        output_format: str = "mp3_44100_128",
        force_instrumental: bool = True,
        model_id: str = "music_v1",
        timeout_seconds: float = 180.0,
    ) -> bytes:
        """Generate one music file and return the audio bytes."""
        length_ms = max(3000, min(int(music_length_ms), 600000))
        payload: Dict[str, Any] = {
            "prompt": prompt,
            "music_length_ms": length_ms,
            "model_id": model_id,
            "force_instrumental": force_instrumental,
        }

        async with httpx.AsyncClient(timeout=timeout_seconds, trust_env=False) as client:
            response = await client.post(
                self.BASE_URL,
                params={"output_format": output_format},
                headers=self._headers(),
                json=payload,
            )

        if response.status_code >= 400:
            detail = response.text
            try:
                data = response.json()
                detail = data.get("detail") or data.get("message") or json.dumps(data, ensure_ascii=False)
            except Exception:
                pass
            raise RuntimeError(f"ElevenLabs Music API error {response.status_code}: {detail}")

        return response.content

    def get_audio_duration(self, audio_path: str) -> float:
        try:
            try:
                from moviepy import AudioFileClip
            except ImportError:
                from moviepy.audio.io.AudioFileClip import AudioFileClip
            clip = AudioFileClip(audio_path)
            duration = float(clip.duration or 0)
            clip.close()
            return duration
        except Exception:
            return 0.0

    def concatenate_tracks(self, track_paths: List[str], output_path: str) -> float:
        if not track_paths:
            raise ValueError("No music tracks to concatenate")

        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        try:
            try:
                from moviepy import AudioFileClip, concatenate_audioclips
            except ImportError:
                from moviepy.audio.io.AudioFileClip import AudioFileClip
                from moviepy.audio.AudioClip import concatenate_audioclips

            clips = [AudioFileClip(path) for path in track_paths]
            final_clip = concatenate_audioclips(clips)
            final_clip.write_audiofile(output_path, logger=None)
            duration = float(final_clip.duration or 0)
            final_clip.close()
            for clip in clips:
                clip.close()
            return duration
        except Exception:
            try:
                from pydub import AudioSegment
            except ImportError as exc:
                raise RuntimeError("MoviePy and pydub concatenation both unavailable") from exc

            combined = AudioSegment.empty()
            for path in track_paths:
                combined += AudioSegment.from_file(path)
            combined.export(output_path, format="mp3")
            return combined.duration_seconds

    async def generate_playlist(
        self,
        project_id: int,
        tracks: List[Dict[str, Any]],
        *,
        target_duration_seconds: int,
        force_instrumental: bool = True,
        output_format: str = "mp3_44100_128",
    ) -> Dict[str, Any]:
        """Generate multiple tracks, concatenate them, and return timeline metadata."""
        if not tracks:
            raise ValueError("Longform music track plan is empty")

        safe_target = max(3, int(target_duration_seconds or 0))
        per_track_seconds = max(15, min(600, round(safe_target / len(tracks))))
        audio_dir = os.path.join(config.OUTPUT_DIR, str(project_id), "assets", "audio", "longform_music")
        os.makedirs(audio_dir, exist_ok=True)

        track_paths: List[str] = []
        timeline: List[Dict[str, Any]] = []
        cursor = 0.0

        for index, track in enumerate(tracks, start=1):
            title = str(track.get("title") or f"Track {index:02d}").strip()
            prompt = str(track.get("prompt") or track.get("music_prompt") or track.get("mood") or title).strip()
            duration_seconds = int(track.get("duration_seconds") or per_track_seconds)
            duration_ms = max(3000, min(duration_seconds * 1000, 600000))
            filename = f"track_{index:02d}_{int(time.time())}.mp3"
            file_path = os.path.join(audio_dir, filename)

            audio_bytes = await self.compose(
                prompt,
                music_length_ms=duration_ms,
                output_format=output_format,
                force_instrumental=force_instrumental,
            )
            with open(file_path, "wb") as f:
                f.write(audio_bytes)

            actual_duration = self.get_audio_duration(file_path) or (duration_ms / 1000.0)
            timeline.append({
                "index": index,
                "title": title,
                "prompt": prompt,
                "start": round(cursor, 2),
                "end": round(cursor + actual_duration, 2),
                "duration": round(actual_duration, 2),
                "file": file_path,
                "url": f"/output/{project_id}/assets/audio/longform_music/{filename}",
            })
            cursor += actual_duration
            track_paths.append(file_path)

        final_path = os.path.join(audio_dir, "playlist_full.mp3")
        total_duration = self.concatenate_tracks(track_paths, final_path)
        return {
            "audio_path": final_path,
            "audio_url": f"/output/{project_id}/assets/audio/longform_music/playlist_full.mp3",
            "duration": round(total_duration, 2),
            "tracks": timeline,
        }


elevenlabs_music_service = ElevenLabsMusicService()
