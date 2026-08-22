import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
WORKER_DIR = ROOT / "worker"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(WORKER_DIR) not in sys.path:
    sys.path.insert(0, str(WORKER_DIR))

import hermes_worker  # noqa: E402
from services.hermes_offline_harness import build_valid_sample_payload  # noqa: E402


class _FakeLog:
    def __init__(self):
        self.messages = []

    def info(self, message):
        self.messages.append(("info", message))

    def warning(self, message):
        self.messages.append(("warning", message))


class _FakeResponse:
    status_code = 204
    text = ""


def test_script_plan_stage_rejects_repeated_scene_summaries():
    structure = {
        "scenes": [
            {
                "scene_summary": "같은 장면이 반복된다",
                "scene_purpose": f"목적 {idx}",
                "retention_hook": f"훅 {idx}",
            }
            for idx in range(4)
        ]
    }

    with pytest.raises(RuntimeError, match="script_plan quality gate failed"):
        hermes_worker._validate_script_plan_stage(
            structure,
            script_style="옛날이야기",
            topic="옛날 마을의 숨겨진 약속",
            upload_title="옛날 마을의 숨겨진 약속",
            image_style="folk tale",
        )


def test_script_plan_stage_rejects_repeated_scene_situations_and_visuals():
    structure = {
        "scenes": [
            {
                "scene_summary": f"unique summary {idx}",
                "scene_purpose": f"unique purpose {idx}",
                "retention_hook": f"unique hook {idx}",
                "scene_situation": (
                    "Timed visual beat 13 (60-75s, 15s). Keep it separate and advance the story: "
                    "the same woodcutter meets the same child in the same yard."
                ),
                "visual_direction": (
                    "Mandatory 15-second development phase cut. Use a distinct composition, action, "
                    "or camera beat. the same warm moonlit yard composition."
                ),
            }
            for idx in range(3)
        ]
    }

    with pytest.raises(RuntimeError, match="script_plan quality gate failed"):
        hermes_worker._validate_script_plan_stage(
            structure,
            script_style="old_story",
            topic="old mountain spirit tale",
            upload_title="woodcutter mountain spirit condition",
            image_style="folk tale",
        )


def test_script_generate_stage_rejects_missing_2x2_grid_prompts():
    payload = build_valid_sample_payload("옛날이야기")
    payload["structure"]["image_grid_prompts"] = []

    with pytest.raises(RuntimeError, match="image_grid_prompts"):
        hermes_worker._validate_script_generate_stage(payload, category="옛날이야기")


def test_script_language_stats_detects_excessive_latin():
    script = ("이 문장은 한국어 대본입니다. " * 80) + ("This English sentence should not dominate the Korean script. " * 40)

    assert hermes_worker._script_has_excessive_latin(script)


def test_korean_language_rescue_script_passes_latin_gate():
    payload = build_valid_sample_payload("탈북사연")
    title = payload["generated_title"]

    script = hermes_worker._build_korean_language_rescue_script(
        title,
        title,
        payload["structure"],
    )
    stats = hermes_worker._script_language_stats(script)

    assert stats["hangul"] >= 1000
    assert not hermes_worker._script_has_excessive_latin(script)


def test_publish_metadata_stage_requires_script_quality_for_quality_gated_job():
    payload = build_valid_sample_payload("옛날이야기")
    payload.pop("script_quality_report", None)
    payload["defer_ready_until_quality_gate"] = True

    with pytest.raises(RuntimeError, match="missing script_quality_report"):
        hermes_worker._validate_publish_metadata_stage(payload, category="옛날이야기")


def test_publish_metadata_stage_accepts_complete_package():
    payload = build_valid_sample_payload("옛날이야기")
    payload["defer_ready_until_quality_gate"] = True

    report = hermes_worker._validate_publish_metadata_stage(payload, category="옛날이야기")

    assert report["status"] == "pass"
    assert report["stage"] == "publish_metadata"


def test_script_generate_defers_supabase_ready_sync_when_quality_gated(monkeypatch):
    import requests

    calls = []

    def fake_patch(*args, **kwargs):
        calls.append((args, kwargs))
        return _FakeResponse()

    monkeypatch.setenv("NEXT_PUBLIC_SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "service-role")
    monkeypatch.setattr(requests, "patch", fake_patch)

    payload = build_valid_sample_payload("옛날이야기")
    payload["topic_queue_id"] = "123"
    payload["defer_ready_until_quality_gate"] = True

    hermes_worker._save_result_to_supabase("script_generate", payload, _FakeLog())

    assert calls == []


def test_publish_metadata_syncs_full_prepared_package_even_when_quality_gated(monkeypatch):
    import requests

    calls = []

    def fake_patch(*args, **kwargs):
        calls.append((args, kwargs))
        return _FakeResponse()

    monkeypatch.setenv("NEXT_PUBLIC_SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "service-role")
    monkeypatch.setattr(requests, "patch", fake_patch)

    payload = build_valid_sample_payload("무협")
    payload.update(
        {
            "topic_queue_id": "3285",
            "topic": "버림받은 삼류무사가 사부의 낡은 검보를 펼친 날",
            "generated_title": "버림받은 삼류무사가 사부의 낡은 검보를 펼친 날",
            "upload_title": "버림받은 삼류무사가 사부의 낡은 검보를 펼친 날",
            "narrative_blueprint": {"protagonist": "삼류무사"},
            "defer_ready_until_quality_gate": True,
        }
    )
    payload["structure"]["main_character"] = {
        "name": "무진",
        "role": "protagonist",
        "visual_dna_en": "Korean swordsman with a lean build and tired eyes",
        "wardrobe_en": "worn gray martial robe",
    }
    payload["structure"]["supporting_characters"] = [
        {
            "name": "사부",
            "role": "mentor",
            "visual_dna_en": "elderly Korean master with white hair",
            "wardrobe_en": "plain dark robe",
        }
    ]

    hermes_worker._save_result_to_supabase("publish_metadata_generate", payload, _FakeLog())

    assert len(calls) == 1
    patch_payload = calls[0][1]["json"]
    assert patch_payload["status"] == "pending"
    assert patch_payload["pregenerated_script"] == payload["script"]
    assert patch_payload["pregenerated_script_status"] == "ready"
    assert patch_payload["pregenerated_structure"] == payload["structure"]
    assert patch_payload["pregenerated_structure_status"] == "ready"
    assert patch_payload["publish_metadata"] == payload["publish_metadata"]
    assert patch_payload["generated_title"] == payload["generated_title"]
    assert patch_payload["total_scenes"] == len(payload["structure"]["scenes"])
    assert patch_payload["progress_payload"]["prepared_topic_ready"] is True
    assert patch_payload["progress_payload"]["main_character"]["name"] == "무진"
    assert patch_payload["progress_payload"]["supporting_characters"][0]["name"] == "사부"
    assert patch_payload["progress_payload"]["character_anchors"]["max_character_anchors"] == 3
