from pathlib import Path
import json
import sys


ROOT = Path(__file__).resolve().parents[1]
WORKER_DIR = ROOT / "worker"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(WORKER_DIR) not in sys.path:
    sys.path.insert(0, str(WORKER_DIR))

import hermes_worker  # noqa: E402
from services.narration_policy import normalize_tts_speed  # noqa: E402


def test_tts_speed_scales_script_target_for_fixed_duration():
    normal_chars, _ = hermes_worker._script_gen_length_instruction(
        15 * 60, False, "senior", "ko", 1.0
    )
    slow_chars, instruction = hermes_worker._script_gen_length_instruction(
        15 * 60, False, "senior", "ko", 0.9
    )

    assert normal_chars == 4500
    assert slow_chars == 4050
    assert "0.90x" in instruction


def test_tts_speed_is_bounded_to_elevenlabs_supported_range():
    assert normalize_tts_speed(None) == 1.0
    assert normalize_tts_speed("0.9") == 0.9
    assert normalize_tts_speed(0.1) == 0.7
    assert normalize_tts_speed(2.0) == 1.2


def test_script_job_uses_worker_saved_speed_when_payload_omits_it(tmp_path, monkeypatch):
    monkeypatch.setattr(hermes_worker, "STATE_DIR", tmp_path)
    (tmp_path / "hermes_autopilot_state.json").write_text(
        json.dumps({"settings": {"tts_speed": 0.9}}),
        encoding="utf-8",
    )
    payload = {
        "topic_queue_id": "123",
        "topic": "테스트 주제",
        "structure": {"scenes": [{"scene_order": 1}]},
        "target_duration_seconds": 900,
    }

    validated = hermes_worker._validate_script_generate_payload(payload)

    assert validated[8] == 0.9


def test_worker_speed_is_propagated_to_user_tts_path():
    required_markers = {
        ROOT / "worker" / "dashboard_app.py": [
            'id="auto-setting-tts-speed"',
            "tts_speed: ttsSpeed",
        ],
        ROOT / "worker" / "hermes_autopilot.py": [
            '"tts_speed": self.settings.get("tts_speed", 1.0)',
        ],
        ROOT / "auth-web" / "app" / "api" / "internal" / "worker" / "jobs" / "[jobId]" / "complete" / "route.ts": [
            "tts_speed: resultPayload.tts_speed",
        ],
        ROOT / "auth-web" / "app" / "api" / "std" / "topics" / "[topicId]" / "claim" / "route.ts": [
            "tts_speed: topic.progress_payload?.tts_speed || 1",
        ],
        ROOT / "auth-web" / "app" / "api" / "std" / "projects" / "[projectId]" / "tts" / "generate" / "route.ts": [
            "speed: projectTtsSpeed",
        ],
    }

    for path, markers in required_markers.items():
        source = path.read_text(encoding="utf-8")
        for marker in markers:
            assert marker in source, f"Missing {marker!r} in {path}"
