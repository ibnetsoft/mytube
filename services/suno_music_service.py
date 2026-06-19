import base64
import json
import time
from typing import Any, Dict

import httpx

from config import config


class SunoMusicService:
    """Configurable REST adapter for Suno-compatible music APIs.

    Suno API providers differ, so SUNO_API_BASE_URL should point to the concrete
    generation endpoint for the provider in use.
    """

    def _endpoint(self) -> str:
        endpoint = (config.SUNO_API_BASE_URL or "").strip()
        if not endpoint:
            raise RuntimeError("Suno API base URL is missing")
        return endpoint

    def _headers(self) -> Dict[str, str]:
        api_key = (config.SUNO_API_KEY or "").strip()
        if not api_key:
            raise RuntimeError("Suno API key is missing")
        return {
            "Authorization": f"Bearer {api_key}",
            "x-api-key": api_key,
            "Content-Type": "application/json",
        }

    async def compose(
        self,
        prompt: str,
        *,
        music_length_ms: int = 30000,
        force_instrumental: bool = True,
        timeout_seconds: float = 240.0,
        **_kwargs: Any,
    ) -> bytes:
        duration_seconds = max(3, int(music_length_ms / 1000))
        payload: Dict[str, Any] = {
            "prompt": prompt,
            "duration_seconds": duration_seconds,
            "make_instrumental": force_instrumental,
            "instrumental": force_instrumental,
            "wait_audio": True,
        }

        async with httpx.AsyncClient(timeout=timeout_seconds, trust_env=False) as client:
            response = await client.post(self._endpoint(), headers=self._headers(), json=payload)

            if response.status_code >= 400:
                detail = response.text
                try:
                    data = response.json()
                    detail = data.get("error") or data.get("message") or json.dumps(data, ensure_ascii=False)
                except Exception:
                    pass
                raise RuntimeError(f"Suno API error {response.status_code}: {detail}")

            content_type = response.headers.get("content-type", "")
            if content_type.startswith("audio/"):
                return response.content

            data = response.json()
            audio_bytes = self._extract_audio_bytes(data)
            if audio_bytes:
                return audio_bytes

            audio_url = self._extract_audio_url(data)
            if not audio_url:
                raise RuntimeError("Suno API response did not include audio data or audio_url")

            audio_response = await client.get(audio_url)
            if audio_response.status_code >= 400:
                raise RuntimeError(f"Suno audio download failed {audio_response.status_code}: {audio_response.text[:200]}")
            return audio_response.content

    def _extract_audio_bytes(self, data: Any) -> bytes:
        for item in self._iter_candidates(data):
            raw = item.get("audio_base64") or item.get("audio") or item.get("base64")
            if isinstance(raw, str) and raw.strip():
                if raw.startswith("data:"):
                    raw = raw.split(",", 1)[-1]
                try:
                    return base64.b64decode(raw)
                except Exception:
                    continue
        return b""

    def _extract_audio_url(self, data: Any) -> str:
        for item in self._iter_candidates(data):
            for key in ("audio_url", "audioUrl", "url", "source_audio_url", "sourceAudioUrl"):
                value = item.get(key)
                if isinstance(value, str) and value.startswith(("http://", "https://")):
                    return value
        return ""

    def _iter_candidates(self, data: Any):
        if isinstance(data, dict):
            yield data
            for key in ("data", "clips", "songs", "items", "result"):
                value = data.get(key)
                if isinstance(value, dict):
                    yield value
                elif isinstance(value, list):
                    for item in value:
                        if isinstance(item, dict):
                            yield item
        elif isinstance(data, list):
            for item in data:
                if isinstance(item, dict):
                    yield item


suno_music_service = SunoMusicService()
