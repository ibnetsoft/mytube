import os
import time
from typing import Any, Dict, List

from config import config
from services.elevenlabs_music_service import elevenlabs_music_service
from services.suno_music_service import suno_music_service


class MusicGenerationService:
    def provider(self) -> str:
        provider = (getattr(config, "MUSIC_PROVIDER", "") or "elevenlabs").strip().lower()
        return provider if provider in {"elevenlabs", "suno"} else "elevenlabs"

    def _service(self):
        return suno_music_service if self.provider() == "suno" else elevenlabs_music_service

    async def compose(self, prompt: str, **kwargs: Any) -> bytes:
        return await self._service().compose(prompt, **kwargs)

    def get_audio_duration(self, audio_path: str) -> float:
        return elevenlabs_music_service.get_audio_duration(audio_path)

    def concatenate_tracks(self, track_paths: List[str], output_path: str) -> float:
        return elevenlabs_music_service.concatenate_tracks(track_paths, output_path)

    async def generate_playlist(
        self,
        project_id: int,
        tracks: List[Dict[str, Any]],
        *,
        target_duration_seconds: int,
        force_instrumental: bool = True,
        output_format: str = "mp3_44100_128",
    ) -> Dict[str, Any]:
        if not tracks:
            raise ValueError("Longform music track plan is empty")

        safe_target = max(3, int(target_duration_seconds or 0))
        per_track_seconds = max(15, min(600, round(safe_target / len(tracks))))
        # NOTE: Save in the "tracks" subdirectory so _discover_generated_tracks() can find them
        audio_dir = os.path.join(config.OUTPUT_DIR, str(project_id), "assets", "audio", "longform_music")
        track_dir = os.path.join(audio_dir, "tracks")
        os.makedirs(track_dir, exist_ok=True)

        track_paths: List[str] = []
        timeline: List[Dict[str, Any]] = []
        cursor = 0.0

        for index, track in enumerate(tracks, start=1):
            title = str(track.get("title") or f"Track {index:02d}").strip()
            prompt = str(track.get("prompt") or track.get("music_prompt") or track.get("mood") or title).strip()
            duration_seconds = int(track.get("duration_seconds") or per_track_seconds)
            duration_ms = max(3000, min(duration_seconds * 1000, 600000))
            # Use nanoseconds to avoid filename collisions when tracks are generated quickly
            filename = f"track_{index:02d}_{time.time_ns()}.mp3"
            file_path = os.path.join(track_dir, filename)

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
                "url": f"/output/{project_id}/assets/audio/longform_music/tracks/{filename}",
                "provider": self.provider(),
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
            "provider": self.provider(),
        }


music_generation_service = MusicGenerationService()
