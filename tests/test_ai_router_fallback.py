import asyncio
import pathlib
import sys

import pytest


ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services import ai_router


def test_deepseek_generation_failure_never_falls_back_to_gemini(monkeypatch):
    fallback_called = False

    async def fake_deepseek_generate_text(*args, **kwargs):
        raise Exception("DeepSeek API error (401): invalid_request_error")

    async def fake_gemini_generate_text(*args, **kwargs):
        nonlocal fallback_called
        fallback_called = True
        return "gemini ok"

    monkeypatch.setattr(ai_router.config, "DEEPSEEK_API_KEY", "bad-key", raising=False)
    monkeypatch.setattr(ai_router.config, "GLM_API_KEY", "", raising=False)
    monkeypatch.setattr(ai_router.deepseek_service, "generate_text", fake_deepseek_generate_text)
    monkeypatch.setattr(ai_router.gemini_service, "generate_text", fake_gemini_generate_text)

    with pytest.raises(RuntimeError, match="no provider fallback is allowed"):
        asyncio.run(
            ai_router.generate_text(
            "prompt",
            "deepseek-chat",
            task_type="scene_media_prompt_generation",
            json_mode=True,
            )
        )

    assert fallback_called is False


def test_deepseek_credit_exhaustion_never_falls_back(monkeypatch):
    fallback_called = False

    async def exhausted_deepseek(*args, **kwargs):
        raise Exception("DeepSeek API error (402): Insufficient Balance")

    async def unexpected_gemini(*args, **kwargs):
        nonlocal fallback_called
        fallback_called = True
        return "must not be used"

    monkeypatch.setattr(ai_router.config, "DEEPSEEK_API_KEY", "exhausted-key", raising=False)
    monkeypatch.setattr(ai_router.config, "GLM_API_KEY", "", raising=False)
    monkeypatch.setattr(ai_router.deepseek_service, "generate_text", exhausted_deepseek)
    monkeypatch.setattr(ai_router.gemini_service, "generate_text", unexpected_gemini)

    with pytest.raises(ai_router.ProviderCreditExhaustedError, match="크레딧 또는 잔액이 부족"):
        asyncio.run(ai_router.generate_text("prompt", "deepseek-chat", task_type="hermes_script_generate"))

    assert fallback_called is False
