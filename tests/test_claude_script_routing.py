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
from worker import hermes_worker


def test_misplaced_claude_key_is_repaired_before_generation(monkeypatch):
    misplaced_key = "sk-ant-test-placeholder"
    monkeypatch.setattr(Config, "CLAUDE_API_KEY", "")
    monkeypatch.setattr(Config, "SCRIPT_GENERATION_MODEL", misplaced_key)
    monkeypatch.delenv("CLAUDE_API_KEY", raising=False)
    monkeypatch.setenv("SCRIPT_GENERATION_MODEL", misplaced_key)

    Config.normalize_generation_models()

    assert Config.CLAUDE_API_KEY == misplaced_key
    assert Config.SCRIPT_GENERATION_MODEL == "claude-haiku-4-5-20251001"


def test_hermes_script_generation_routes_haiku_to_claude():
    model = hermes_worker._select_script_draft_model(
        Config,
        "claude-haiku-4-5-20251001",
    )

    assert model == "claude-haiku-4-5-20251001"
    assert ai_router.detect_provider(model) == "claude"
