import base64
import json
from typing import Any, Dict

import httpx

from config import config


class GeminiMusicService:
    """REST adapter for Gemini/Vertex Lyria music generation."""

    def _model(self) -> str:
        return (config.MUSIC_GEMINI_MODEL or "lyria-3-pro-preview").strip()

    def _project_id(self) -> str:
        return (config.MUSIC_GEMINI_PROJECT_ID or "").strip()

    def _location(self) -> str:
        return (config.MUSIC_GEMINI_LOCATION or "global").strip() or "global"

    def _endpoint(self) -> str:
        model = self._model()
        custom = (config.MUSIC_GEMINI_BASE_URL or "").strip()
        if custom:
            return custom.format(
                model=model,
                project_id=self._project_id(),
                location=self._location(),
            )

        project_id = self._project_id()
        if not project_id:
            raise RuntimeError("Gemini music project ID is missing")

        if model == "lyria-002":
            return (
                f"https://{self._location()}-aiplatform.googleapis.com/v1/"
                f"projects/{project_id}/locations/{self._location()}/publishers/google/models/{model}:predict"
            )
        return f"https://aiplatform.googleapis.com/v1beta1/projects/{project_id}/locations/{self._location()}/interactions"

    def _headers(self) -> Dict[str, str]:
        api_key = (config.GEMINI_API_KEY or "").strip()
        if not api_key:
            raise RuntimeError("Gemini API key or access token is missing")
        return {
            "Authorization": f"Bearer {api_key}",
            "x-goog-api-key": api_key,
            "Content-Type": "application/json; charset=utf-8",
        }

    def _payload(self, prompt: str, duration_seconds: int, force_instrumental: bool) -> Dict[str, Any]:
        model = self._model()
        prompt_text = prompt
        if force_instrumental and "instrumental" not in prompt.lower():
            prompt_text = f"{prompt}. Instrumental only, no vocals."

        if model == "lyria-002":
            return {
                "instances": [{"prompt": prompt_text}],
                "parameters": {"sample_count": 1},
            }

        return {
            "model": model,
            "input": [{"type": "text", "text": prompt_text}],
            "parameters": {
                "duration_seconds": duration_seconds,
                "sample_count": 1,
            },
        }

    async def compose(
        self,
        prompt: str,
        *,
        music_length_ms: int = 30000,
        force_instrumental: bool = True,
        timeout_seconds: float = 600.0,
        **_kwargs: Any,
    ) -> bytes:
        duration_seconds = max(3, int(music_length_ms / 1000))
        payload = self._payload(prompt, duration_seconds, force_instrumental)

        async with httpx.AsyncClient(timeout=timeout_seconds, trust_env=False) as client:
            response = await client.post(self._endpoint(), headers=self._headers(), json=payload)

            if response.status_code >= 400:
                detail = response.text
                try:
                    data = response.json()
                    detail = data.get("error") or data.get("message") or json.dumps(data, ensure_ascii=False)
                except Exception:
                    pass
                raise RuntimeError(f"Gemini music API error {response.status_code}: {detail}")

            content_type = response.headers.get("content-type", "")
            if content_type.startswith("audio/"):
                return response.content

            audio_bytes = self._extract_audio_bytes(response.json())
            if not audio_bytes:
                raise RuntimeError("Gemini music response did not include audio data")
            return audio_bytes

    def _extract_audio_bytes(self, data: Any) -> bytes:
        for item in self._iter_candidates(data):
            raw = (
                item.get("audioContent")
                or item.get("audio_content")
                or item.get("audio_base64")
                or item.get("data")
            )
            item_type = str(item.get("type") or "")
            mime_type = str(item.get("mime_type") or item.get("mimeType") or "")
            if isinstance(raw, str) and (item_type == "audio" or mime_type.startswith("audio/") or "audioContent" in item):
                if raw.startswith("data:"):
                    raw = raw.split(",", 1)[-1]
                try:
                    return base64.b64decode(raw)
                except Exception:
                    continue
        return b""

    def _iter_candidates(self, data: Any):
        if isinstance(data, dict):
            yield data
            for key in ("outputs", "predictions", "data", "result", "items"):
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


gemini_music_service = GeminiMusicService()
