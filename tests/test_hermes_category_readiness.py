import pathlib
import sys
import json
import asyncio

import pytest


ROOT = pathlib.Path(__file__).resolve().parents[1]
WORKER = ROOT / "worker"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(WORKER) not in sys.path:
    sys.path.insert(0, str(WORKER))

from worker import hermes_autopilot
from worker import hermes_worker


TARGET_CATEGORIES = ["옛날이야기", "황혼19금", "탈북사연"]


def test_worker_start_categories_are_normalized_for_dashboard_start_path():
    manager = hermes_autopilot.HermesAutopilotManager()

    assert manager._normalize_active_categories(TARGET_CATEGORIES) == TARGET_CATEGORIES


def test_retired_categories_are_removed_from_remote_cache_and_saved_settings():
    manager = object.__new__(hermes_autopilot.HermesAutopilotManager)
    manager.remote_categories = {
        "노후금융": {"id": 8, "name": "노후금융"},
        "경제": {"id": 3, "name": "경제"},
        "숨은퇴출항목": {"id": 8, "name": "숨은퇴출항목"},
        "한국사연": {"id": 5, "name": "한국사연"},
    }
    manager.settings = {
        "category_image_style_overrides": {
            "노후금융": "realistic",
            "경제": "cinematic",
            "한국사연": "watercolor",
        }
    }

    categories = manager.get_all_categories()
    overrides = manager._normalize_category_image_style_overrides(
        manager.settings["category_image_style_overrides"]
    )

    assert "노후금융" not in categories
    assert "경제" not in categories
    assert "숨은퇴출항목" not in categories
    assert overrides == {"한국사연": "watercolor"}


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


def test_autopilot_status_reconciles_stale_running_memory(monkeypatch, tmp_path):
    state_path = tmp_path / "hermes_autopilot_state.json"
    state_path.write_text(
        json.dumps(
            {
                "is_running": False,
                "current_step": "completed",
                "current_category": "황혼19금",
                "current_topic": "완료된 주제",
                "last_run_status": "completed",
                "last_error": "",
                "logs": ["완료"],
                "settings": {},
                "session_stats": {"generated_count": 1},
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(hermes_autopilot, "STATE_FILE", state_path)
    monkeypatch.setattr(hermes_autopilot.job_store, "list_jobs", lambda limit=100: [])

    manager = object.__new__(hermes_autopilot.HermesAutopilotManager)
    manager.is_running = True
    manager.current_step = "유튜브 탐색 및 고성과 분석"
    manager.current_category = "황혼19금"
    manager.current_topic = ""
    manager.current_topic_queue_id = ""
    manager.current_image_style = ""
    manager.last_run_status = "running"
    manager.last_error = ""
    manager.last_completed_result_id = ""
    manager.logs = []
    manager.settings = {}
    manager.session_stats = {"generated_count": 0}
    manager._apply_settings = lambda *args, **kwargs: None
    manager._save_state = lambda: None

    status = manager.get_status()

    assert status["is_running"] is False
    assert status["last_run_status"] == "completed"
    assert status["current_step"] == "completed"
    assert status["session_stats"]["generated_count"] == 1


def test_autopilot_status_hydrates_running_state_saved_by_another_process(monkeypatch, tmp_path):
    state_path = tmp_path / "hermes_autopilot_state.json"
    state_path.write_text(
        json.dumps(
            {
                "is_running": True,
                "current_step": "[category-a] preparing",
                "current_category": "category-a",
                "current_topic": "topic-a",
                "last_run_status": "running",
                "last_error": "",
                "logs": ["started"],
                "settings": {"mode": "target_limit", "target_limit": 1},
                "session_stats": {"generated_count": 0},
                "updated_at": 1000,
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(hermes_autopilot, "STATE_FILE", state_path)
    monkeypatch.setattr(hermes_autopilot.time, "time", lambda: 1005)
    monkeypatch.setattr(hermes_autopilot.job_store, "list_jobs", lambda limit=100: [])

    manager = object.__new__(hermes_autopilot.HermesAutopilotManager)
    manager.is_running = False
    manager.current_step = "idle"
    manager.current_category = ""
    manager.current_topic = ""
    manager.current_topic_queue_id = ""
    manager.current_image_style = ""
    manager.last_run_status = "idle"
    manager.last_error = ""
    manager.last_completed_result_id = ""
    manager.logs = []
    manager.settings = {"mode": "target_limit", "target_limit": 1}
    manager.session_stats = {"generated_count": 0}
    manager._apply_settings = lambda *args, **kwargs: None

    status = manager.get_status()

    assert status["is_running"] is True
    assert status["last_run_status"] == "running"
    assert status["current_step"] == "[category-a] preparing"
    assert status["current_category"] == "category-a"


def test_autopilot_start_is_idempotent_when_another_process_is_running(monkeypatch, tmp_path):
    state_path = tmp_path / "hermes_autopilot_state.json"
    state_path.write_text(
        json.dumps(
            {
                "is_running": True,
                "current_step": "[category-a] preparing",
                "last_run_status": "running",
                "updated_at": 1000,
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(hermes_autopilot, "STATE_FILE", state_path)
    monkeypatch.setattr(hermes_autopilot.time, "time", lambda: 1005)
    monkeypatch.setattr(hermes_autopilot.job_store, "list_jobs", lambda limit=100: [])

    manager = object.__new__(hermes_autopilot.HermesAutopilotManager)
    manager._lock = asyncio.Lock()
    manager.is_running = False
    manager.current_step = "idle"
    manager.current_category = ""
    manager.current_topic = ""
    manager.current_topic_queue_id = ""
    manager.current_image_style = ""
    manager.last_run_status = "idle"
    manager.last_error = ""
    manager.last_completed_result_id = ""
    manager.logs = []
    manager.settings = {"mode": "target_limit", "target_limit": 1, "active_categories": ["category-a"]}
    manager.session_stats = {"generated_count": 0}
    manager._apply_settings = lambda *args, **kwargs: None

    result = asyncio.run(manager.start({"mode": "target_limit", "target_limit": 1}))

    assert result == {"success": True, "already_running": True}
    assert manager.is_running is True


def test_autopilot_status_promotes_completed_resume_pipeline(monkeypatch, tmp_path):
    state_path = tmp_path / "hermes_autopilot_state.json"
    state_path.write_text(
        json.dumps(
            {
                "is_running": False,
                "current_step": "failed",
                "last_run_status": "failed",
                "updated_at": 1000,
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(hermes_autopilot, "STATE_FILE", state_path)
    monkeypatch.setattr(
        hermes_autopilot.job_store,
        "list_jobs",
        lambda limit=100: [
            {
                "job_id": "metadata-job",
                "source": "autopilot",
                "job_type": "publish_metadata_generate",
                "status": hermes_autopilot.job_store.COMPLETED,
                "completed_at": 2000,
                "payload": {
                    "category": "황혼19금",
                    "topic": "완료된 주제",
                },
            }
        ],
    )

    manager = object.__new__(hermes_autopilot.HermesAutopilotManager)
    manager.is_running = False
    manager.current_step = "failed"
    manager.current_category = "황혼19금"
    manager.current_topic = ""
    manager.current_topic_queue_id = ""
    manager.current_image_style = ""
    manager.last_run_status = "failed"
    manager.last_error = "old error"
    manager.last_completed_result_id = ""
    manager.logs = []
    manager.settings = {}
    manager.session_stats = {"generated_count": 0}
    manager._apply_settings = lambda *args, **kwargs: None

    status = manager.get_status()

    assert status["is_running"] is False
    assert status["last_run_status"] == "completed"
    assert status["current_step"] == "completed"
    assert status["last_error"] == ""
    assert status["last_completed_result_id"] == "metadata-job"
    assert status["current_topic"] == "완료된 주제"


def test_category_autopilot_resumes_unfinished_pipeline_before_new_topic(monkeypatch):
    submitted = {}

    jobs = [
        {
            "job_id": "failed-script",
            "job_type": "script_generate",
            "status": "FAILED",
            "created_at": 30,
            "completed_at": 40,
            "payload": {
                "topic_queue_id": "queue-1",
                "category": "탈북사연",
                "topic": "멈춘 탈북사연 제목",
            },
        },
        {
            "job_id": "plan-job",
            "job_type": "script_plan_generate",
            "status": "COMPLETED",
            "created_at": 20,
            "completed_at": 25,
            "payload": {
                "topic_queue_id": "queue-1",
                "category": "탈북사연",
                "topic": "멈춘 탈북사연 제목",
            },
        },
        {
            "job_id": "research-job",
            "job_type": "web_research",
            "status": "COMPLETED",
            "created_at": 10,
            "completed_at": 15,
            "payload": {
                "topic_queue_id": "queue-1",
                "category": "탈북사연",
                "upload_title": "멈춘 탈북사연 제목",
            },
        },
    ]

    def fake_submit_job(**kwargs):
        submitted.update(kwargs)
        return "new-script-job"

    monkeypatch.setattr(hermes_autopilot.job_store, "list_jobs", lambda limit=500: jobs)
    monkeypatch.setattr(hermes_autopilot.job_store, "submit_job", fake_submit_job)

    manager = object.__new__(hermes_autopilot.HermesAutopilotManager)
    manager.settings = {"target_duration_seconds_by_category": {}, "start_new_pipeline": False}
    manager._read_result_file = lambda job_id: {
        "topic_queue_id": "queue-1",
        "category": "탈북사연",
        "upload_title": "멈춘 탈북사연 제목",
        "structure": {"scenes": [{"scene_order": 1}]},
        "script_style": "dramatic_single",
        "image_style": "realistic",
        "title_generation": {"generated_title": "멈춘 탈북사연 제목"},
    } if job_id == "plan-job" else None

    pipeline = manager._existing_unfinished_pipeline_for_category("탈북사연")
    result = manager._submit_resume_job_from_pipeline(pipeline)

    assert result["success"] is True
    assert result["resumed_stage"] == "script_generate"
    assert submitted["job_type"] == "script_generate"
    assert submitted["payload"]["topic_queue_id"] == "queue-1"
    assert submitted["payload"]["resume_from_job_id"] == "plan-job"


def test_category_autopilot_can_bypass_resume_when_explicit_new_pipeline(monkeypatch):
    monkeypatch.setattr(
        hermes_autopilot.job_store,
        "list_jobs",
        lambda limit=500: [
            {
                "job_id": "plan-job",
                "job_type": "script_plan_generate",
                "status": "COMPLETED",
                "created_at": 1,
                "completed_at": 2,
                "payload": {"category": "탈북사연", "topic": "멈춘 제목"},
            }
        ],
    )

    manager = object.__new__(hermes_autopilot.HermesAutopilotManager)
    manager.settings = {"start_new_pipeline": True}
    manager.is_running = True

    assert asyncio.run(manager._resume_existing_category_pipeline_if_any("탈북사연")) is False


def test_all_script_plan_jobs_require_real_scene_planner_output():
    assert hermes_worker._requires_strict_scene_planner_success({"source": "autopilot", "payload": {}})
    assert hermes_worker._requires_strict_scene_planner_success({"source": "manual", "payload": {}})


def test_fallback_scene_plan_builds_slots_without_ai_output():
    with pytest.raises(RuntimeError, match="Synthetic scene-plan fallback is disabled"):
        hermes_worker._build_fallback_scene_plan("topic", "title", 120, "default", "", {}, {})


def test_long_fallback_scene_plan_does_not_trip_repetition_qa():
    with pytest.raises(RuntimeError, match="Synthetic scene-plan fallback is disabled"):
        hermes_worker._build_fallback_scene_plan("topic", "title", 9000, "default", "", {}, {})


def test_fallback_scene_plan_uses_category_when_style_is_generic():
    with pytest.raises(RuntimeError, match="Synthetic scene-plan fallback is disabled"):
        hermes_worker._build_fallback_scene_plan("topic", "title", 120, "default", "", {}, {}, "story")


def test_non_economy_category_fallbacks_do_not_use_economy_copy():
    with pytest.raises(RuntimeError, match="Synthetic scene-plan fallback is disabled"):
        hermes_worker._build_fallback_scene_plan("topic", "title", 120, "default", "", {}, {})


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
    with pytest.raises(RuntimeError, match="Synthetic narration fallback is disabled"):
        hermes_worker._fallback_narration_section("topic", "title", {}, 1, 1, 100)


def test_target_categories_have_title_styles_and_safe_fallbacks():
    with pytest.raises(RuntimeError, match="Synthetic category title fallback is disabled"):
        hermes_autopilot.HermesAutopilotManager()._category_fallback_title("옛날이야기")


def test_target_categories_have_rss_relevance_terms():
    for category in TARGET_CATEGORIES:
        terms = hermes_worker.RSS_RELEVANCE_TERMS_BY_CATEGORY.get(category)

        assert terms, f"{category} must have RSS relevance terms"
        assert category in terms


def test_twilight_has_local_rss_channel_pool():
    manager = hermes_autopilot.HermesAutopilotManager()

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


def test_scene_plan_repetition_allows_reused_voice_direction():
    beats = ["arrival", "warning", "choice", "betrayal", "rescue", "return"]
    structure = {
        "scenes": [
            {
                "scene_summary": f"The {beat} changes the story",
                "scene_situation": f"A distinct {beat} situation unfolds",
                "scene_purpose": f"Advance the {beat} conflict",
                "retention_hook": f"What follows the {beat}?",
                "end_bridge": f"The {beat} opens a new consequence",
                "tts_direction": "조용하고 감정적인 나레이션",
            }
            for beat in beats
        ]
    }

    assert not hermes_worker._scene_plan_repetition_errors(structure)


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


def test_supported_story_categories_have_repetition_repair_handlers_and_pass_qa():
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
    
    # 1. 무협
    martial_rep = hermes_worker._repair_martial_scene_plan_repetition(repeated_structure, "강호 비급", "강호 전설의 비급")
    assert not hermes_worker._scene_plan_repetition_errors(martial_rep)
    
    # 2. 탈북사연
    survival_rep = hermes_worker._repair_survival_story_scene_plan_repetition(repeated_structure, "두만강 국경", "두만강 탈출 실화")
    assert not hermes_worker._scene_plan_repetition_errors(survival_rep)
    
    # 3. 황혼19금
    twilight_rep = hermes_worker._repair_twilight_scene_plan_repetition(repeated_structure, "황혼 재회", "30년 만의 황혼 재회")
    assert not hermes_worker._scene_plan_repetition_errors(twilight_rep)
    
    # 4. 한국사연
    korean_rep = hermes_worker._repair_korean_drama_scene_plan_repetition(repeated_structure, "시댁 갈등", "시댁의 무리한 요구를 응징한 사연")
    assert not hermes_worker._scene_plan_repetition_errors(korean_rep)
    
    # 5. 해외감동
    overseas_rep = hermes_worker._repair_overseas_touching_scene_plan_repetition(repeated_structure, "외국인 은인", "타국에서 만난 참전용사 은인")
    assert not hermes_worker._scene_plan_repetition_errors(overseas_rep)
    
    # 6. 옛날이야기
    old_rep = hermes_worker._repair_old_story_scene_plan_repetition(repeated_structure, "조선시대 야담", "조선시대 야담 실화")
    assert not hermes_worker._scene_plan_repetition_errors(old_rep)


def test_supported_story_categories_have_visual_motifs_refreshed():
    base_structure = {
        "scenes": [
            {"scene_summary": f"장면 {i}", "scene_purpose": "목적", "retention_hook": "훅"}
            for i in range(1, 13)
        ]
    }
    all_categories = ["무협", "탈북사연", "황혼19금", "한국사연", "해외감동", "옛날이야기"]
    for cat in all_categories:
        refreshed = hermes_worker._refresh_scene_visual_fields_for_category(cat, base_structure, f"{cat} 주제", f"{cat} 제목")
        scenes = refreshed.get("scenes") or []
        assert len(scenes) == 12
        for scene in scenes:
            assert scene.get("visual_direction")
            assert scene.get("tts_direction")
            assert scene.get("end_bridge")


def test_supported_story_categories_have_rescue_scripts():
    structure = {"scenes": [{"scene_summary": "장면 1"}]}
    assert len(hermes_worker._build_martial_rescue_script("무협", "무협 복수극", structure)) >= 1000
    assert len(hermes_worker._build_survival_rescue_script("탈북사연", "두만강 탈출", structure)) >= 1000
    assert len(hermes_worker._build_twilight_rescue_script("황혼19금", "황혼의 사랑", structure)) >= 1000
    assert len(hermes_worker._build_korean_drama_rescue_script("한국사연", "사이다 응징", structure)) >= 1000
    assert len(hermes_worker._build_overseas_rescue_script("해외감동", "해외 은인 재회", structure)) >= 1000
    assert len(hermes_worker._build_old_story_grave_vigil_rescue_script("옛날이야기", "무덤 지킨 며느리", structure)) >= 1000
