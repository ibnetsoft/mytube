import copy
import sys
from pathlib import Path
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts import repair_active_materials as repair
from worker.senior_script_guard import CHECKS


def fixture_package():
    text = "객잔 주인은 문 앞에 선 낯선 손님에게 따뜻한 차를 건넸지요."
    old = {"scene_text": text, "image_url": "https://example.test/scene.png", "metadata": {"storage_path": "keep.png"}}
    scene = {**copy.deepcopy(old), "image_prompt": "A watercolor inn scene with an innkeeper offering tea to a traveler beside a wooden table, soft warm lamplight, 16:9, no text, no watermark.",
        "video_prompt": "A watercolor inn scene. The innkeeper slowly sets a steaming tea bowl on the wooden table in front of the traveler. Preserve faces, costume and the original composition for this single 5-second shot. Camera: slow push-in. No cuts. no dialogue, no narration, no subtitles, no captions, no music, no sound effects, no audio",
        "scene_summary": "주인이 손님을 맞는다."}
    report = {"profile": "senior_listening_v3", "verdict": "pass", "score": 90, "critical_issues": [],
        "checks": {k: {"pass": True, "evidence": "Scene 1 identifies the innkeeper and traveler through an action."} for k in CHECKS}}
    material = {"verdict": "pass", "critical_issues": [], "checks": {k: {"pass": True, "evidence": "Scene 1 image and narration both show the innkeeper offering tea."}
        for k in ("title_payoff", "engagement", "prompt_alignment", "character_continuity", "metadata_accuracy")}}
    return {"structure": {"scenes": [scene]}, "script_quality_report": report, "material_quality_report": material,
        "publish_metadata": {"description": "소개" * 70, "tags": ["이야기"]}}, {"category_id": 2, "pregenerated_structure": {"scenes": [old]}}


def test_repair_cannot_replace_existing_image():
    package, original = fixture_package()
    repair.validate_package(package, original)
    package["structure"]["scenes"][0]["image_url"] = "replacement"
    with pytest.raises(ValueError, match="existing media changed"):
        repair.validate_package(package, original)


def test_narration_only_cannot_change_visual_prompts():
    package, original = fixture_package()
    package["repair_scope"] = "narration_only"
    original["pregenerated_structure"]["scenes"][0].update({k: package["structure"]["scenes"][0][k] for k in ("image_prompt", "video_prompt")})
    repair.validate_package(package, original)
    package["structure"]["scenes"][0]["image_prompt"] = "different visual"
    with pytest.raises(ValueError, match="cannot change image_prompt"):
        repair.validate_package(package, original)


def test_incomplete_independent_review_is_rejected():
    package, original = fixture_package()
    package["material_quality_report"]["checks"].pop("character_continuity")
    with pytest.raises(ValueError, match="character_continuity"):
        repair.validate_package(package, original)


def test_grids_use_repaired_prompts_and_preserve_mapping():
    structure = {"scenes": [{"image_prompt": f"repaired {i}"} for i in range(5)],
        "image_grid_prompts": [{"prompt": "stale", "batch_id": "keep"}]}
    repair.refresh_grids(structure)
    assert structure["image_grid_prompts"][0]["batch_id"] == "keep"
    assert "stale" not in str(structure)
    assert [p["scene_number"] for g in structure["image_grid_prompts"] for p in g["panels"]] == [1, 2, 3, 4, 2, 3, 4, 5]
    assert all("Position: Bottom-Right" in g["prompt"] for g in structure["image_grid_prompts"])


def test_grid_readiness_matches_production_contract():
    from services.image_grid_prompts import validate_image_grid_prompt_readiness
    structure = {"scenes": [{"scene_order": i, "image_prompt": f"Scene {i}: " + "Specific approved appearance and scene action. " * 4} for i in range(1, 54)]}
    repair.refresh_grids(structure)
    validate_image_grid_prompt_readiness(structure["scenes"], structure["image_grid_prompts"], status="ready", require_compact_template=True)
    assert structure["image_grid_prompts"][-1]["scene_numbers"] == [50, 51, 52, 53]


def test_subtitle_edits_are_preserved():
    p = {"project_payload": {"script": "원본 대본", "original_worker_script": "원본 대본", "subtitles": [{"text": "수정 대본"}]}}
    assert repair.user_script_changed(p, "원본 대본")
    p["project_payload"]["subtitles"] = [{"text": "원본"}, {"text": "대본"}]
    assert not repair.user_script_changed(p, "원본 대본")


def test_targeted_blueprint_patch_preserves_other_ledgers():
    old = {"continuity_ledger": {"cast": [{"name": "old"}], "timeline": [1, 2]}, "scene_count": 28}
    result = repair.merge_patch(old, {"continuity_ledger": {"cast": [{"name": "corrected"}]}})
    assert result["continuity_ledger"]["timeline"] == [1, 2]
    assert result["scene_count"] == 28
    assert old["continuity_ledger"]["cast"][0]["name"] == "old"


def test_legacy_target_duration_does_not_require_reallocated_schedule():
    assert repair.resolve_repair_duration({"target_duration": 5}, {"repaired_scene_durations": []}, 0, 53) == 5
    assert repair.resolve_repair_duration({"target_duration": 30}, {}, 52, 53) == 30
    with pytest.raises(ValueError, match="Missing scene timing"):
        repair.resolve_repair_duration({}, {"repaired_scene_durations": [5]}, 2, 53)
    assert repair.resolve_repair_duration({}, {"repaired_scene_durations": [5, 15]}, 1, 2) == 15


def test_submitted_projects_block_all_writes(monkeypatch):
    package, row = fixture_package()
    row["id"] = 1
    monkeypatch.setattr(repair, "fetch", lambda table, **kw: [row] if table == "topics_queue" else [{"status": "review_requested"}])
    monkeypatch.setattr(repair, "patch_row", lambda *a: pytest.fail("Submitted work must not be modified"))
    with pytest.raises(RuntimeError, match="Submitted/completed"):
        repair.publish(row, package)


def test_project_only_images_survive_topic_repair():
    old = {"scenes": [{"scene_number": 1, "scene_text": "old", "image_url": "user-image", "video_url": "user-video", "metadata": {"storage_path": "user/path"}}]}
    new = {"scenes": [{"scene_number": 1, "scene_text": "new", "image_url": "topic-image", "metadata": {}}]}
    result = repair.merge_structure(old, new)
    assert result["scenes"][0]["scene_text"] == "new"
    assert result["scenes"][0]["image_url"] == "user-image"
    assert result["scenes"][0]["video_url"] == "user-video"
    assert result["scenes"][0]["metadata"]["storage_path"] == "user/path"
    assert old["scenes"][0]["scene_text"] == "old"


def test_project_variant_uses_current_subtitle_edits_without_touching_source():
    project = {"id": "project", "topic_queue_id": 7, "category_id": 2, "title": "제목",
        "source_payload": {"id": 7, "pregenerated_script": "old"},
        "project_payload": {"structure": {"scenes": [{"scene_number": 1, "scene_text": "old", "image_url": "keep"}]},
            "subtitles": [{"scene_number": 1, "text": "유저가 고친 문장"}]}}
    row = repair.project_variant(project)
    assert row["pregenerated_script"] == "유저가 고친 문장"
    assert row["pregenerated_structure"]["scenes"][0]["image_url"] == "keep"
    assert row["_project_only_id"] == "project"
    assert project["source_payload"]["pregenerated_script"] == "old"
