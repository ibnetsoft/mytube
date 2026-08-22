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


def test_autopilot_plan_jobs_can_use_scene_planner_fallback():
    assert not hermes_worker._requires_strict_scene_planner_success({"source": "autopilot", "payload": {}})
    assert not hermes_worker._requires_strict_scene_planner_success(
        {"source": "manual", "payload": {"defer_ready_until_quality_gate": True}}
    )
    assert hermes_worker._requires_strict_scene_planner_success(
        {"source": "manual", "payload": {"require_scene_planner_success": True}}
    )
    assert not hermes_worker._requires_strict_scene_planner_success({"source": "manual", "payload": {}})


def test_fallback_scene_plan_builds_slots_without_ai_output():
    structure = hermes_worker._build_fallback_scene_plan(
        topic="황혼19금",
        upload_title="아내가 남긴 일기장 속에서 발견한 40년 전 첫사랑의 편지",
        target_duration=120,
        script_style="황혼 story",
        style_directive="",
        benchmark_analysis={"title": "reference"},
        title_generation={},
    )

    assert structure["scene_count"] == len(structure["scenes"])
    assert structure["scenes"]
    assert structure["scenes"][0]["time_range"] == "0-5s"
    assert structure["planner_notes"]["fallback"] is True


def test_long_fallback_scene_plan_does_not_trip_repetition_qa():
    structure = hermes_worker._build_fallback_scene_plan(
        topic="황혼19금",
        upload_title="아내가 남긴 일기장 속에서 발견한 40년 전 첫사랑의 편지",
        target_duration=9000,
        script_style="story",
        style_directive="",
        benchmark_analysis={"title": "reference"},
        title_generation={},
    )

    assert not hermes_worker._scene_plan_repetition_errors(structure)


def test_twilight_repair_keeps_long_scene_plan_unique():
    scenes = [
        {
            "scene_summary": "반복 장면",
            "scene_purpose": "반복 목적",
            "retention_hook": "반복 질문",
            "scene_situation": "반복 상황",
        }
        for _ in range(80)
    ]
    structure = {"scenes": scenes, "scene_count": len(scenes), "planner_notes": {}}

    repaired = hermes_worker._repair_twilight_scene_plan_repetition(
        structure,
        topic="황혼19금",
        upload_title="아내가 남긴 일기장 속에서 발견한 40년 전 첫사랑의 편지",
    )

    assert not hermes_worker._scene_plan_repetition_errors(repaired)


def test_fallback_narration_section_avoids_repeated_fillers():
    scene = {
        "scene_summary": "낡은 편지를 발견한 남편이 아내의 비밀을 의심한다",
        "scene_situation": "황혼의 집 안에서 일기장과 편지가 발견된다",
        "scene_purpose": "숨겨진 사연의 첫 단서를 제시한다",
        "retention_hook": "편지의 주인은 누구였을까",
    }

    text = hermes_worker._fallback_narration_section(
        topic="황혼19금",
        upload_title="아내가 남긴 일기장 속에서 발견한 40년 전 첫사랑의 편지",
        scene=scene,
        idx=42,
        total=258,
        min_chars=1400,
    )

    assert not hermes_worker._detect_repeated_script_sentences(text, max_allowed=3)


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


def test_all_8_categories_have_repetition_repair_handlers_and_pass_qa():
    repeated_structure = {
        "scenes": [
            {
                "scene_summary": "같은 장면 요약이 계속 반복된다",
                "scene_purpose": "같은 목적",
                "retention_hook": "같은 훅",
            }
            for _ in range(14)
        ]
    }
    
    # 1. 노후금융
    finance_rep = hermes_worker._repair_finance_scene_plan_repetition(repeated_structure, "노후연금", "노후연금 이야기")
    assert not hermes_worker._scene_plan_repetition_errors(finance_rep)
    
    # 2. 경제
    econ_rep = hermes_worker._repair_macro_economy_scene_plan_repetition(repeated_structure, "환율 금리", "환율 금리 폭등")
    assert not hermes_worker._scene_plan_repetition_errors(econ_rep)
    
    # 3. 무협
    martial_rep = hermes_worker._repair_martial_scene_plan_repetition(repeated_structure, "강호 비급", "강호 전설의 비급")
    assert not hermes_worker._scene_plan_repetition_errors(martial_rep)
    
    # 4. 탈북사연
    survival_rep = hermes_worker._repair_survival_story_scene_plan_repetition(repeated_structure, "두만강 국경", "두만강 탈출 실화")
    assert not hermes_worker._scene_plan_repetition_errors(survival_rep)
    
    # 5. 황혼19금
    twilight_rep = hermes_worker._repair_twilight_scene_plan_repetition(repeated_structure, "황혼 재회", "30년 만의 황혼 재회")
    assert not hermes_worker._scene_plan_repetition_errors(twilight_rep)
    
    # 6. 한국사연
    korean_rep = hermes_worker._repair_korean_drama_scene_plan_repetition(repeated_structure, "시댁 갈등", "시댁의 무리한 요구를 응징한 사연")
    assert not hermes_worker._scene_plan_repetition_errors(korean_rep)
    
    # 7. 해외감동
    overseas_rep = hermes_worker._repair_overseas_touching_scene_plan_repetition(repeated_structure, "외국인 은인", "타국에서 만난 참전용사 은인")
    assert not hermes_worker._scene_plan_repetition_errors(overseas_rep)
    
    # 8. 옛날이야기
    old_rep = hermes_worker._repair_old_story_scene_plan_repetition(repeated_structure, "조선시대 야담", "조선시대 야담 실화")
    assert not hermes_worker._scene_plan_repetition_errors(old_rep)


def test_all_8_categories_have_visual_motifs_refreshed():
    base_structure = {
        "scenes": [
            {"scene_summary": f"장면 {i}", "scene_purpose": "목적", "retention_hook": "훅"}
            for i in range(1, 13)
        ]
    }
    all_categories = ["노후금융", "경제", "무협", "탈북사연", "황혼19금", "한국사연", "해외감동", "옛날이야기"]
    for cat in all_categories:
        refreshed = hermes_worker._refresh_scene_visual_fields_for_category(cat, base_structure, f"{cat} 주제", f"{cat} 제목")
        scenes = refreshed.get("scenes") or []
        assert len(scenes) == 12
        for scene in scenes:
            assert scene.get("visual_direction")
            assert scene.get("tts_direction")
            assert scene.get("end_bridge")


def test_all_8_categories_have_rescue_scripts():
    structure = {"scenes": [{"scene_summary": "장면 1"}]}
    assert len(hermes_worker._build_finance_rescue_script("노후금융", "노후금융 제목", structure)) >= 1000
    assert len(hermes_worker._build_economy_rescue_script("경제", "경제 지표 분석", structure)) >= 1000
    assert len(hermes_worker._build_martial_rescue_script("무협", "무협 복수극", structure)) >= 1000
    assert len(hermes_worker._build_survival_rescue_script("탈북사연", "두만강 탈출", structure)) >= 1000
    assert len(hermes_worker._build_twilight_rescue_script("황혼19금", "황혼의 사랑", structure)) >= 1000
    assert len(hermes_worker._build_korean_drama_rescue_script("한국사연", "사이다 응징", structure)) >= 1000
    assert len(hermes_worker._build_overseas_rescue_script("해외감동", "해외 은인 재회", structure)) >= 1000
    assert len(hermes_worker._build_old_story_grave_vigil_rescue_script("옛날이야기", "무덤 지킨 며느리", structure)) >= 1000
