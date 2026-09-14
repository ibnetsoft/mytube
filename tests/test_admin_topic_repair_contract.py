from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_topic_repair_uses_inline_confirmation_instead_of_browser_dialog():
    source = (ROOT / "auth-web/components/DashboardContent.tsx").read_text(encoding="utf-8")

    assert "topicRepairConfirmId" in source
    assert "isConfirmingRepair ? '확정 실행' : 'Repair'" in source
    assert "confirm(`${targetMinutes}분 / ${targetSceneCount}씬" not in source


def test_topic_repair_requires_a_complete_worker_package():
    source = (ROOT / "auth-web/app/api/admin/topics-queue/repair/route.ts").read_text(encoding="utf-8")

    assert "non-empty narration, image_prompt, and video_prompt" in source
    assert "Calibrate the total narration length" in source
    assert "Run the final script quality gate and require a passing report" in source
    assert "generate the final publish metadata package" in source


def test_topic_repair_preserves_existing_duration_and_scene_defaults():
    source = (ROOT / "auth-web/app/api/admin/topics-queue/repair/route.ts").read_text(encoding="utf-8")

    assert "recommended_duration_minutes" in source
    assert "total_scenes" in source
    assert "const fallbackMinutes" in source
    assert "const previousSceneCount" in source


def test_topic_repair_rejects_duplicate_active_pipeline():
    source = (ROOT / "auth-web/app/api/admin/topics-queue/repair/route.ts").read_text(encoding="utf-8")

    assert ".in('job_type', ['script_plan_generate', 'script_generate', 'publish_metadata_generate'])" in source
    assert ".contains('payload', { topic_queue_id: topicId, repair_mode: true })" in source
    assert "An active repair job already exists" in source
