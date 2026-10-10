"""DeepSeek text-generation provider.

Uses DeepSeek's OpenAI-compatible chat completions API for text-only
generation. Gemini-specific features such as Google Search grounding, Imagen,
and Veo remain on the Gemini provider.
"""
import json
import time

import httpx

from config import config


DEFAULT_DEEPSEEK_MODEL = "deepseek-chat"


class DeepSeekService:
    def __init__(self):
        self.default_base_url = "https://api.deepseek.com/v1"

    @property
    def api_key(self) -> str:
        return (getattr(config, "DEEPSEEK_API_KEY", "") or "").strip()

    @property
    def base_url(self) -> str:
        base = (getattr(config, "DEEPSEEK_BASE_URL", "") or self.default_base_url).strip()
        return base.rstrip("/")

    async def generate_text(
        self,
        prompt: str,
        *,
        model: str = DEFAULT_DEEPSEEK_MODEL,
        temperature: float = 0.7,
        max_tokens: int = 8192,
        task_type: str = "text_gen",
        json_mode: bool = False,
        project_id: int = None,
    ) -> str:
        if not self.api_key:
            raise Exception("DEEPSEEK_API_KEY is not configured.")

        selected_model = (model or DEFAULT_DEEPSEEK_MODEL).strip()
        payload = {
            "model": selected_model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if json_mode:
            payload["response_format"] = {"type": "json_object"}

        url = f"{self.base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        start_time = time.time()
        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.post(url, headers=headers, json=payload)
        elapsed = time.time() - start_time

        if response.status_code >= 400:
            try:
                detail = response.json()
                detail_text = json.dumps(detail, ensure_ascii=False)
            except Exception:
                detail_text = response.text
            try:
                import database as db
                db.add_ai_log(
                    project_id,
                    task_type,
                    selected_model,
                    "deepseek",
                    "failed",
                    prompt_summary=prompt[:100],
                    error_msg=detail_text[:500],
                    elapsed_time=elapsed,
                )
            except Exception:
                pass
            raise Exception(f"DeepSeek API error ({response.status_code}) for {task_type}: {detail_text[:500]}")

        data = response.json()
        try:
            text = data["choices"][0]["message"]["content"] or ""
            usage = data.get("usage") or {}
            try:
                import database as db
                db.add_ai_log(
                    project_id,
                    task_type,
                    selected_model,
                    "deepseek",
                    "success",
                    prompt_summary=prompt[:100],
                    input_tokens=usage.get("prompt_tokens", 0),
                    output_tokens=usage.get("completion_tokens", 0),
                    elapsed_time=elapsed,
                )
            except Exception:
                pass
            return text
        except Exception:
            raise Exception(f"DeepSeek API returned an unexpected response for {task_type}: {str(data)[:500]}")


deepseek_service = DeepSeekService()
