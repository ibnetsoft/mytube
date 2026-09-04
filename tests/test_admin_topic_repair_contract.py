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
