import sys
import asyncio
from pathlib import Path

import pytest


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


def test_script_generation_batches_standard_scenes_into_few_act_chunks():
    scenes = [{"scene_number": idx + 1, "scene_summary": f"scene {idx + 1}"} for idx in range(53)]
    budgets = [{"duration_seconds": 20, "min_chars": 80, "max_chars": 160} for _ in scenes]

    chunks = hermes_worker._chunk_scenes_for_script_generation(scenes, budgets, max_chunks=4)

    assert 1 < len(chunks) <= 4
    assert chunks[0][0] == 0
    assert sum(len(chunk_scenes) for _, chunk_scenes, _ in chunks) == 53


def test_script_chunk_prompt_excludes_scene_meta_and_tts_fields():
    scene = {
        "scene_order": 1,
        "scene_summary": "오프닝 금기 장면에서 '산속 옹기장이가 항아리 하나를 절대 팔지 않은 이유'의 약속을 1단계로 밀어 올리며, 마을 입구의 낡은 금기패가 사건의 시작을 알린다",
        "scene_situation": "오프닝의 역할은 같은 사건 반복이 아니라 단서를 전진시키는 것이다. 금기 때문에 마을 사람들의 숨겨진 관계가 한 겹 더 흔들린다",
        "scene_purpose": "낡은 금기패를 통해 옹기장이의 비밀을 시작한다",
        "scene_emotion": "불길함",
        "tts_direction": "할머니가 옛이야기를 들려주듯 말한다. 설명보다 사건으로 느끼게 하고 여운으로 넘긴다.",
        "title_promise_link": "제목의 약속을 회수한다",
        "end_bridge": "다음 단서는 같은 문장으로 이어진다.",
    }
    prompt = hermes_worker._build_script_chunk_prompt(
        "산속 옹기장이가 항아리 하나를 절대 팔지 않은 이유",
        [scene],
        [{"scene_order": 1, "duration_seconds": 5, "target_chars": 80, "min_chars": 40, "max_chars": 120}],
        False,
        False,
        [],
        "900초 분량",
        "ko",
        upload_title="산속 옹기장이가 항아리 하나를 절대 팔지 않은 이유",
        structure_context={"title_promise": "항아리의 비밀을 밝힌다"},
        narrative_blueprint={},
        previous_context={},
    )

    assert "tts_direction" not in prompt
    assert "end_bridge" not in prompt
    assert "title_promise_link" not in prompt
    assert "1단계로 밀어 올리며" not in prompt
    assert "숨겨진 관계가 한 겹 더 흔들린다" not in prompt
    assert "story_beat" in prompt
    assert "낡은 금기패" in prompt






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






def test_script_scene_payload_carries_drama_fields_without_visual_tts():
    scene = {
        "scene_order": 1,
        "scene_summary": "돌쇠가 금기의 첫 증거를 발견한다",
        "scene_purpose": "사건을 먼저 보여준다",
        "retention_hook": "이 증거는 누구의 것일까?",
        "dramatic_function": "opening incident and personal stake",
        "character_choice": "돌쇠가 증거를 숨기지 않고 확인하러 간다",
        "emotional_shift": "호기심이 책임감으로 바뀐다",
        "reveal_or_question": "마을의 침묵이 거짓일 수 있다",
        "visual_direction": "must not leak",
        "tts_direction": "must not leak",
    }

    payload = hermes_worker._scene_payload_for_script(
        scene,
        {"duration_seconds": 5, "target_chars": 80, "min_chars": 40, "max_chars": 120},
        "",
    )

    assert payload["dramatic_function"] == "opening incident and personal stake"
    assert payload["character_choice"] == "돌쇠가 증거를 숨기지 않고 확인하러 간다"
    assert payload["emotional_shift"] == "호기심이 책임감으로 바뀐다"
    assert payload["reveal_or_question"] == "마을의 침묵이 거짓일 수 있다"
    assert "visual_direction" not in payload
    assert "tts_direction" not in payload
