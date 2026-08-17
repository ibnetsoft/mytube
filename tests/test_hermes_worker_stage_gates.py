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
