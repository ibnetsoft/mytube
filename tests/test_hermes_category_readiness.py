import pathlib
import sys
import json


ROOT = pathlib.Path(__file__).resolve().parents[1]
WORKER = ROOT / "worker"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(WORKER) not in sys.path:
    sys.path.insert(0, str(WORKER))

from worker import hermes_autopilot
from worker import hermes_worker


TARGET_CATEGORIES = ["경제", "노후금융", "옛날이야기", "황혼19금", "탈북사연"]


def test_worker_start_categories_are_normalized_for_dashboard_start_path():
    manager = hermes_autopilot.HermesAutopilotManager()

    assert manager._normalize_active_categories(TARGET_CATEGORIES) == TARGET_CATEGORIES


def test_target_limit_reached_uses_numeric_limit_and_count():
    manager = object.__new__(hermes_autopilot.HermesAutopilotManager)
    manager.settings = {"mode": "target_limit", "target_limit": "1"}
    manager.session_stats = {"generated_count": 1}

    assert manager._target_limit_reached()


def test_target_limit_quality_failure_stops_without_retrying_new_title():
    manager = object.__new__(hermes_autopilot.HermesAutopilotManager)
    manager.settings = {"mode": "target_limit", "target_limit": 1}
    manager.session_stats = {"generated_count": 0}
    manager.logs = []
    manager.add_log = lambda message: manager.logs.append(message)
    manager._save_state = lambda: None
    manager.is_running = True
    manager.current_step = "running"
    manager.last_run_status = "running"
    manager.last_error = ""

    stopped = manager._stop_after_target_limit_failure(RuntimeError("quality failed"))

    assert stopped is True
    assert manager.is_running is False
    assert manager.last_run_status == "failed"
    assert manager.current_step == "failed"
    assert "another title" in manager.logs[-1]


def test_autopilot_plan_jobs_require_strict_scene_planner_success():
    assert hermes_worker._requires_strict_scene_planner_success({"source": "autopilot", "payload": {}})
    assert hermes_worker._requires_strict_scene_planner_success(
        {"source": "manual", "payload": {"defer_ready_until_quality_gate": True}}
    )
    assert not hermes_worker._requires_strict_scene_planner_success({"source": "manual", "payload": {}})


def test_target_categories_have_title_styles_and_safe_fallbacks():
    manager = hermes_autopilot.HermesAutopilotManager()

    for category in TARGET_CATEGORIES:
        style = manager._category_title_style(category)
        fallback = manager._category_fallback_title(category)

        assert style
        assert fallback
        assert manager._is_usable_title_candidate(fallback, category)


def test_target_categories_have_rss_relevance_terms():
    for category in TARGET_CATEGORIES:
        terms = hermes_worker.RSS_RELEVANCE_TERMS_BY_CATEGORY.get(category)

        assert terms, f"{category} must have RSS relevance terms"
        assert category in terms


def test_economy_and_twilight_have_local_rss_channel_pools():
    manager = hermes_autopilot.HermesAutopilotManager()

    assert len(manager._load_local_benchmark_channels("경제")) >= 8
    assert len(manager._load_local_benchmark_channels("황혼19금")) >= 8


def test_old_story_plan_repair_does_not_use_survival_story_beats():
    structure = {
        "scenes": [
            {
                "scene_summary": "같은 장면",
                "scene_purpose": "같은 목적",
                "retention_hook": "같은 훅",
            }
            for _ in range(12)
        ]
    }

    repaired = hermes_worker._repair_old_story_scene_plan_repetition(
        structure,
        "아들 삼형제가 어머니의 유언을 어기고 무덤을 팠다",
        "아들 삼형제가 어머니의 유언을 어기고 무덤을 팠다",
    )

    assert not hermes_worker._scene_plan_repetition_errors(repaired)
    blob = json.dumps(repaired, ensure_ascii=False)
    for forbidden in ("탈북", "북한", "두만강", "국경", "보위부", "브로커", "safehouse", "defector"):
        assert forbidden not in blob


def test_scene_plan_repetition_detects_same_summary_with_different_hooks():
    structure = {
        "scenes": [
            {
                "scene_summary": "The woodcutter walks back up the mountain at sunset.",
                "scene_purpose": f"purpose {idx}",
                "retention_hook": f"hook {idx}",
            }
            for idx in range(4)
        ]
    }

    errors = hermes_worker._scene_plan_repetition_errors(structure)

    assert any("repeats one summary" in error for error in errors)


def test_old_story_grave_vigil_repair_matches_daughter_in_law_title():
    structure = {
        "scenes": [
            {
                "scene_summary": "같은 장면",
                "scene_purpose": "같은 목적",
                "retention_hook": "같은 훅",
            }
            for _ in range(16)
        ]
    }

    repaired = hermes_worker._repair_old_story_scene_plan_repetition(
        structure,
        "며느리가 시어머니 묘에 3년을 묻고 산 이유",
        "며느리가 시어머니 묘에 3년을 묻고 산 이유, 마을 사람들은 아무도 몰랐다",
    )

    assert not hermes_worker._scene_plan_repetition_errors(repaired)
    blob = json.dumps(repaired, ensure_ascii=False)
    assert "며느리" in blob
    assert "시어머니" in blob
    assert "중반 전환" not in blob
    for forbidden in ("세 형제", "첫째", "둘째", "막내", "아들 삼형제"):
        assert forbidden not in blob


def test_old_story_scene_plan_rejects_survival_category_contamination():
    contaminated = {
        "scenes": [
            {
                "scene_summary": "세 형제가 두만강 국경 근처에서 숨어 기다린다",
                "scene_purpose": "북한 탈출의 긴장을 만든다",
                "retention_hook": "브로커는 약속 장소에 올까?",
            },
            {
                "scene_summary": "보위부 추격을 피해 safehouse로 이동한다",
                "scene_purpose": "탈북민 가족의 생존 위험을 보여준다",
                "retention_hook": "중국 공안이 문을 두드리면 어떻게 될까?",
            },
        ]
    }

    errors = hermes_worker._scene_plan_category_contamination_errors(
        contaminated,
        script_style="old_story",
        topic="아들 삼형제가 어머니의 유언을 어기고 무덤을 팠다",
        upload_title="아들 삼형제가 어머니의 유언을 어기고 무덤을 팠다",
        image_style="folk tale hanok village",
    )

    assert errors
    assert "survival/defector contamination" in errors[0]


def test_survival_story_repair_context_is_not_generic_story_fallback():
    assert not hermes_worker._is_survival_story_plan_context(
        "old_story",
        "아들 삼형제가 어머니의 유언을 어기고 무덤을 팠다",
        "아들 삼형제가 어머니의 유언을 어기고 무덤을 팠다",
        "folk tale hanok village",
    )
    assert hermes_worker._is_survival_story_plan_context(
        "탈북사연",
        "두만강을 건넌 가족의 마지막 선택",
        "보위부 추격을 피해 살아남은 가족",
        "documentary testimony",
    )


def test_old_story_category_context_detects_default_script_style_payload():
    assert hermes_worker._is_old_story_plan_context(
        "default 옛날이야기",
        "머느리가 시어머니 묘에 3년을 묻고 산 이유",
        "머느리가 시어머니 묘에 3년을 묻고 산 이유, 마을 사람들은 아무도 몰랐다",
        "realistic",
    )
    assert hermes_worker._is_old_story_plan_context(
        "default",
        "머느리가 시어머니 묘에 3년을 묻고 산 이유",
        "머느리가 시어머니 묘에 3년을 묻고 산 이유, 마을 사람들은 아무도 몰랐다",
        "realistic",
    )


def test_old_story_context_repairs_mojibake_title_for_retry_jobs():
    title = "며느리가 시어머니 묘에 3년을 묻고 산 이유, 마을 사람들은 아무도 몰랐다"
    mojibake_title = title.encode("utf-8").decode("latin1")

    assert hermes_worker._is_old_story_plan_context(
        "story",
        mojibake_title,
        mojibake_title,
        "3d_render",
    )
