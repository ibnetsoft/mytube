"""
Claude API 서비스 - 대본 생성에 Anthropic Claude 사용
"""
import httpx
from typing import Optional, List
from config import config


DEFAULT_CLAUDE_MODEL = "claude-sonnet-4-6"
CLAUDE_MODEL_OPTIONS = [
    "claude-sonnet-5",
    "claude-sonnet-4-6",      # 최신 Sonnet (기본)
    "claude-opus-4-8",        # 최신 Opus (고성능)
    "claude-haiku-4-5-20251001",  # Haiku (빠름)
    "claude-3-5-sonnet-20241022",  # 이전 버전 Sonnet
    "claude-3-opus-20240229",      # 이전 버전 Opus
]


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

        if model not in CLAUDE_MODEL_OPTIONS:
            self.log_debug(f"⚠️ [Claude] Unknown model: {model}, using default: {DEFAULT_CLAUDE_MODEL}")
            model = DEFAULT_CLAUDE_MODEL

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
            async with httpx.AsyncClient(timeout=180.0) as client:
                response = await client.post(url, json=payload, headers=headers)
                result = response.json()

                if "content" in result and result["content"]:
                    text = result["content"][0].get("text", "")
                    usage = result.get("usage", {})
                    in_tokens = usage.get('input_tokens', 0)
                    out_tokens = usage.get('output_tokens', 0)

                    elapsed = time.time() - start_time

                    self.log_debug(f"✅ [Claude Text] Success ({elapsed:.1f}s)")

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
            self.log_debug(f"❌ [Claude Text] Exception: {e}")

            import database as db
            db.add_ai_log(
                project_id, task_type, model, 'anthropic', 'failed',
                prompt_summary=prompt[:100],
                error_msg=str(e),
                elapsed_time=elapsed
            )
            raise e


# 전역 인스턴스
import time
claude_service = ClaudeService()