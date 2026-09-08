import asyncio
import pathlib
import sys


ROOT = pathlib.Path(__file__).resolve().parents[1]
WORKER = ROOT / "worker"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(WORKER) not in sys.path:
    sys.path.insert(0, str(WORKER))

from config import Config
from services import ai_router
from worker.hermes_autopilot import HermesAutopilotManager


def test_hermes_control_calls_use_dedicated_models(monkeypatch):
    captured = {}

    async def fake_generate_text(prompt, model, **kwargs):
        captured.update({"prompt": prompt, "model": model, **kwargs})
        return "[]"

    monkeypatch.setattr(Config, "HERMES_ORCHESTRATOR_MODEL", "deepseek-chat")
    monkeypatch.setattr(
        Config,
        "HERMES_ORCHESTRATOR_FALLBACK_MODEL",
        "gemini-3.6-flash",
    )
    monkeypatch.setattr(ai_router, "generate_text", fake_generate_text)

    manager = HermesAutopilotManager()
    asyncio.run(manager._discover_benchmark_keywords("한국사연"))

    assert captured["model"] == "deepseek-chat"
    assert captured["fallback_model"] == "gemini-3.6-flash"
    assert captured["task_type"] == "hermes_benchmark_keyword_discovery"


def test_content_generation_models_remain_independent(monkeypatch):
    monkeypatch.setattr(Config, "HERMES_ORCHESTRATOR_MODEL", "deepseek-chat")
    monkeypatch.setattr(
        Config,
        "HERMES_ORCHESTRATOR_FALLBACK_MODEL",
        "gemini-3.6-flash",
    )
    monkeypatch.setattr(Config, "TOPIC_GENERATION_MODEL", "gemini-3.6-flash")
    monkeypatch.setattr(Config, "TITLE_GENERATION_MODEL", "gemini-3.6-flash")
    monkeypatch.setattr(Config, "SCRIPT_PLANNING_MODEL", "gemini-3.6-flash")
    monkeypatch.setattr(Config, "SCRIPT_GENERATION_MODEL", "claude-haiku-4-5-20251001")
    monkeypatch.setattr(Config, "IMAGE_PROMPT_MODEL", "gemini-3.6-flash")

    assert Config.HERMES_ORCHESTRATOR_MODEL == "deepseek-chat"
    assert Config.TOPIC_GENERATION_MODEL == "gemini-3.6-flash"
    assert Config.TITLE_GENERATION_MODEL == "gemini-3.6-flash"
    assert Config.SCRIPT_PLANNING_MODEL == "gemini-3.6-flash"
    assert Config.SCRIPT_GENERATION_MODEL == "claude-haiku-4-5-20251001"
    assert Config.IMAGE_PROMPT_MODEL == "gemini-3.6-flash"
