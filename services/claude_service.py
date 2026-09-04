"""
Claude API 서비스 - 대본 생성에 Anthropic Claude 사용
"""
import httpx
import time
from typing import Optional, List
from config import config


DEFAULT_CLAUDE_MODEL = "claude-haiku-4-5-20251001"
CLAUDE_MODEL_OPTIONS = [
    "claude-haiku-4-5-20251001",
    "claude-haiku-4-5",
    "claude-sonnet-5",
    "claude-sonnet-4-6",
    "claude-opus-5",
    "claude-fable-5",
    "claude-3-5-haiku-20241022",
    "claude-3-5-sonnet-20241022",
    "claude-3-opus-20240229",
]

def normalize_claude_model_name(model_name: str) -> str:
    """Map human/UI names and aliases (e.g. claude-Haiku-4.5) to valid Anthropic API models."""
    raw = str(model_name or "").strip()
    lower = raw.lower().replace("_", "-").replace(" ", "-")
    
    if "haiku-4" in lower or "haiku-4.5" in lower or "haiku-4-5" in lower or "haiku" in lower:
        return "claude-haiku-4-5-20251001"
    if "sonnet-4-6" in lower:
        return "claude-sonnet-4-6"
    if "sonnet-5" in lower:
        return "claude-sonnet-5"
    if "sonnet" in lower:
        return "claude-3-5-sonnet-20241022"
    if "opus-5" in lower:
        return "claude-opus-5"
    if "opus" in lower:
        return "claude-3-opus-20240229"
    if raw in CLAUDE_MODEL_OPTIONS:
        return raw
    return DEFAULT_CLAUDE_MODEL




class ClaudeService:
    def __init__(self):
        self.base_url = "https://api.anthropic.com/v1"
        self._client = None
        self._api_key = None

    @property
    def api_key(self):
        """Claude API 키 반환 (Supabase global_settings에서 로드)"""
        # 먼저 config에서 확인
        key = getattr(config, 'CLAUDE_API_KEY', None)
        if key:
            return key

        # 없으면 환경변수에서 확인
        import os
        return os.getenv("CLAUDE_API_KEY", "")

    def log_debug(self, msg: str):
        """디버그 로그 출력"""
        try:
            print(msg)
        except Exception:
            pass
        try:
            from datetime import datetime
            with open(config.DEBUG_LOG_PATH, "a", encoding="utf-8") as f:
                f.write(f"[{datetime.now()}] [Claude] {msg}\n")
        except Exception:
            pass

    async def generate_text(
        self,
        prompt: str,
        temperature: float = 0.7,
        max_tokens: int = 8192,
        project_id: int = None,
        task_type: str = "script_gen",
        model: str = DEFAULT_CLAUDE_MODEL
    ) -> str:
        """텍스트 생성"""
        if not self.api_key:
            raise Exception("Claude API 키가 설정되지 않았습니다. 어드민 웹에서 키를 저장한 후 앱을 재시작하세요.")

        target_model = normalize_claude_model_name(model)
        self.log_debug(f"💬 [Claude] Requested model: '{model}' -> Using API model: '{target_model}'")
        model = target_model

        url = f"{self.base_url}/messages"

        headers = {
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json"
        }

        payload = {
            "model": model,
            "max_tokens": max_tokens,
            "messages": [
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            "temperature": temperature
        }

        start_time = time.time()
        try:
            self.log_debug(f"💬 [Claude Text] Starting generation (model={model}, prompt={prompt[:100]}...)")
            request_timeout = 900.0 if max_tokens >= 32768 else (600.0 if max_tokens >= 16384 else 180.0)
            async with httpx.AsyncClient(timeout=request_timeout) as client:
                response = await client.post(url, json=payload, headers=headers)
                result = response.json()

                if "content" in result and result["content"]:
                    text = result["content"][0].get("text", "")
                    usage = result.get("usage", {})
                    in_tokens = usage.get('input_tokens', 0)
                    out_tokens = usage.get('output_tokens', 0)
                    stop_reason = result.get("stop_reason")

                    elapsed = time.time() - start_time

                    self.log_debug(
                        f"✅ [Claude Text] Success ({elapsed:.1f}s, "
                        f"output_tokens={out_tokens}, stop_reason={stop_reason})"
                    )

                    if stop_reason == "max_tokens":
                        raise Exception(
                            f"Claude output truncated at max_tokens={max_tokens} "
                            f"(output_tokens={out_tokens})"
                        )

                    # 로그 기록
                    import database as db
                    db.add_ai_log(
                        project_id, task_type, model, 'anthropic', 'success',
                        prompt_summary=prompt[:100],
                        input_tokens=in_tokens,
                        output_tokens=out_tokens,
                        elapsed_time=elapsed
                    )

                    return text
                else:
                    elapsed = time.time() - start_time
                    error_msg = result.get('error', {}).get('message', str(result)) if isinstance(result.get('error'), dict) else str(result)

                    self.log_debug(f"❌ [Claude Text] Failed: {error_msg}")

                    import database as db
                    db.add_ai_log(
                        project_id, task_type, model, 'anthropic', 'failed',
                        prompt_summary=prompt[:100],
                        error_msg=error_msg,
                        elapsed_time=elapsed
                    )

                    raise Exception(f"Claude API 오류: {error_msg}")
        except httpx.HTTPStatusError as e:
            elapsed = time.time() - start_time
            error_msg = f"HTTP {e.response.status_code}: {e.response.text[:200]}"
            self.log_debug(f"❌ [Claude Text] HTTP Error: {error_msg}")

            import database as db
            db.add_ai_log(
                project_id, task_type, model, 'anthropic', 'failed',
                prompt_summary=prompt[:100],
                error_msg=error_msg,
                elapsed_time=elapsed
            )
            raise Exception(f"Claude HTTP 오류: {error_msg}")
        except Exception as e:
            elapsed = time.time() - start_time
            error_detail = str(e) or type(e).__name__
            self.log_debug(f"❌ [Claude Text] Exception: {error_detail}")

            import database as db
            db.add_ai_log(
                project_id, task_type, model, 'anthropic', 'failed',
                prompt_summary=prompt[:100],
                error_msg=error_detail,
                elapsed_time=elapsed
            )
            raise e


# 전역 인스턴스
claude_service = ClaudeService()
