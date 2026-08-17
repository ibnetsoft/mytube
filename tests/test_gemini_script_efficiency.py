import sys
import asyncio
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKER_DIR = ROOT / "worker"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(WORKER_DIR) not in sys.path:
    sys.path.insert(0, str(WORKER_DIR))

from services import ai_router  # noqa: E402
import hermes_worker  # noqa: E402
import hermes_autopilot  # noqa: E402


def test_explicit_gemini_model_is_not_replaced_by_deepseek(monkeypatch):
    monkeypatch.setattr(ai_router.config, "DEEPSEEK_API_KEY", "test-deepseek-key")
    monkeypatch.setattr(ai_router.config, "GLM_API_KEY", "test-glm-key")

    assert ai_router.normalize_model("gemini-3-flash-preview") == "gemini-3-flash-preview"
    assert ai_router.detect_provider(ai_router.normalize_model("gemini-3-flash-preview")) == "gemini"


def test_unavailable_gemini_models_stay_on_gemini_provider(monkeypatch):
    monkeypatch.setattr(ai_router.config, "DEEPSEEK_API_KEY", "test-deepseek-key")

    normalized = ai_router.normalize_model("gemini-2.5-pro")

    assert normalized == "gemini-3-flash-preview"
    assert ai_router.detect_provider(normalized) == "gemini"


def test_script_generation_can_batch_all_standard_scenes_into_one_call():
    scenes = [{"scene_number": idx + 1, "scene_summary": f"scene {idx + 1}"} for idx in range(53)]
    budgets = [{"min_chars": 80, "max_chars": 160} for _ in scenes]

    chunks = hermes_worker._chunk_scenes_for_script_generation(scenes, budgets, max_chunks=1)

    assert len(chunks) == 1
    assert chunks[0][0] == 0
    assert len(chunks[0][1]) == 53


def test_gemini_generation_failure_does_not_fallback_to_deepseek(monkeypatch):
    monkeypatch.setattr(ai_router.config, "DEEPSEEK_API_KEY", "test-deepseek-key")

    async def fail_gemini(*args, **kwargs):
        raise RuntimeError("gemini unavailable")

    async def fail_if_deepseek_called(*args, **kwargs):
        raise AssertionError("DeepSeek must not be called for explicit Gemini jobs")

    monkeypatch.setattr(ai_router.gemini_service, "generate_text", fail_gemini)
    monkeypatch.setattr(ai_router.deepseek_service, "generate_text", fail_if_deepseek_called)

    try:
        asyncio.run(ai_router.generate_text("prompt", "gemini-3-flash-preview", task_type="hermes_script_generate"))
    except RuntimeError as exc:
        assert "gemini unavailable" in str(exc)
    else:
        raise AssertionError("Gemini failure should be visible to the caller")


def test_autopilot_forces_single_quality_attempt_for_cost_control():
    manager = object.__new__(hermes_autopilot.HermesAutopilotManager)
    manager.settings = {"quality_max_attempts": 3, "target_limit": 1, "min_buffer_per_category": 1}

    manager._apply_settings({})

    assert manager.settings["quality_max_attempts"] == 1
