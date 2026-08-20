import asyncio
import pathlib
import sys


ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services import ai_router


def test_deepseek_generation_falls_back_to_gemini(monkeypatch):
    captured = {}

    async def fake_deepseek_generate_text(*args, **kwargs):
        raise Exception("DeepSeek API error (401): invalid_request_error")

    async def fake_gemini_generate_text(*args, **kwargs):
        captured.update(kwargs)
        return "gemini ok"

    monkeypatch.setattr(ai_router.config, "DEEPSEEK_API_KEY", "bad-key", raising=False)
    monkeypatch.setattr(ai_router.config, "GLM_API_KEY", "", raising=False)
    monkeypatch.setattr(ai_router.deepseek_service, "generate_text", fake_deepseek_generate_text)
    monkeypatch.setattr(ai_router.gemini_service, "generate_text", fake_gemini_generate_text)

    result = asyncio.run(
        ai_router.generate_text(
            "prompt",
            "deepseek-chat",
            task_type="scene_media_prompt_generation",
            json_mode=True,
        )
    )

    assert result == "gemini ok"
    assert captured["model"] == ai_router.FALLBACK_GEMINI_MODEL
    assert captured["task_type"] == "scene_media_prompt_generation"
    assert captured["json_mode"] is True
