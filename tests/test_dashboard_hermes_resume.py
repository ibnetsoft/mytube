import pathlib
import sys


ROOT = pathlib.Path(__file__).resolve().parents[1]
WORKER = ROOT / "worker"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(WORKER) not in sys.path:
    sys.path.insert(0, str(WORKER))

from worker import dashboard_app


def test_resolve_job_by_dashboard_short_id(monkeypatch):
    full_job = {
        "job_id": "0f591bd3-d8b7-4503-b506-479d8e7dd94d",
        "job_type": "script_generate",
        "status": "FAILED",
        "payload": {},
    }

    monkeypatch.setattr(dashboard_app.job_store, "get_job", lambda job_id: None)
    monkeypatch.setattr(dashboard_app.job_store, "list_jobs", lambda limit=100: [full_job])

    assert dashboard_app._resolve_job_by_id_or_prefix("0f591bd3") == full_job


def test_resolve_job_by_short_id_rejects_ambiguous_prefix(monkeypatch):
    monkeypatch.setattr(dashboard_app.job_store, "get_job", lambda job_id: None)
    monkeypatch.setattr(
        dashboard_app.job_store,
        "list_jobs",
        lambda limit=100: [
            {"job_id": "0f591bd3-d8b7-4503-b506-479d8e7dd94d"},
            {"job_id": "0f591bd3-1111-4503-b506-479d8e7dd94d"},
        ],
    )

    assert dashboard_app._resolve_job_by_id_or_prefix("0f591bd3") is None


def test_resume_from_completed_plan_submits_script_job(monkeypatch):
    submitted = {}

    def fake_submit_job(**kwargs):
        submitted.update(kwargs)
        return "new-script-job"

    monkeypatch.setattr(dashboard_app.job_store, "submit_job", fake_submit_job)
    monkeypatch.setattr(
        dashboard_app,
        "_read_job_result",
        lambda job_id: {
            "topic_queue_id": "3285",
            "category": "무협",
            "upload_title": "버림받은 삼류무사가 사부의 낡은 검보를 펼친 날",
            "structure": [{"scene": 1, "beat": "검보를 펼친다"}],
            "image_style": "classic vintage cinema",
            "title_generation": {"generated_title": "버림받은 삼류무사가 사부의 낡은 검보를 펼친 날"},
            "learning_profile": {"category": "무협"},
        },
    )

    result = dashboard_app._submit_resume_job_from_pipeline(
        [
            {
                "job_id": "plan-job",
                "job_type": "script_plan_generate",
                "status": "COMPLETED",
                "payload": {"topic_queue_id": "3285", "category": "무협"},
            }
        ]
    )

    assert result == {
        "success": True,
        "job_id": "new-script-job",
        "resumed_stage": "script_generate",
    }
    assert submitted["job_type"] == "script_generate"
    assert submitted["source"] == "autopilot"
    assert submitted["payload"]["topic_queue_id"] == "3285"
    assert submitted["payload"]["structure"] == [{"scene": 1, "beat": "검보를 펼친다"}]
    assert submitted["payload"]["resume_from_job_id"] == "plan-job"
    assert submitted["payload"]["resume_from_checkpoint"] is True


def test_resume_from_completed_script_submits_metadata_job(monkeypatch):
    submitted = {}

    def fake_submit_job(**kwargs):
        submitted.update(kwargs)
        return "new-metadata-job"

    monkeypatch.setattr(dashboard_app.job_store, "submit_job", fake_submit_job)
    monkeypatch.setattr(
        dashboard_app,
        "_read_job_result",
        lambda job_id: {
            "topic_queue_id": "3285",
            "category": "무협",
            "upload_title": "버림받은 삼류무사가 사부의 낡은 검보를 펼친 날",
            "script": "완성된 대본",
            "structure": [{"scene": 1, "beat": "검보를 펼친다"}],
            "script_quality_report": {"verdict": "pass"},
        },
    )

    result = dashboard_app._submit_resume_job_from_pipeline(
        [
            {
                "job_id": "script-job",
                "job_type": "script_generate",
                "status": "COMPLETED",
                "payload": {"topic_queue_id": "3285", "category": "무협"},
            }
        ]
    )

    assert result == {
        "success": True,
        "job_id": "new-metadata-job",
        "resumed_stage": "publish_metadata_generate",
    }
    assert submitted["job_type"] == "publish_metadata_generate"
    assert submitted["source"] == "autopilot"
    assert submitted["payload"]["script"] == "완성된 대본"
    assert submitted["payload"]["resume_from_job_id"] == "script-job"


def test_resume_rejects_pipeline_without_completed_artifact():
    result = dashboard_app._submit_resume_job_from_pipeline(
        [
            {
                "job_id": "benchmark-job",
                "job_type": "topic_benchmark_analyze",
                "status": "COMPLETED",
                "payload": {"topic_queue_id": "3285", "category": "무협"},
            }
        ]
    )

    assert result["success"] is False
    assert "이어갈 수 있는 완료 단계" in result["error"]


def test_resume_from_completed_web_research_submits_plan_job(monkeypatch):
    submitted = {}

    def fake_submit_job(**kwargs):
        submitted.update(kwargs)
        return "new-plan-job"

    monkeypatch.setattr(dashboard_app.job_store, "submit_job", fake_submit_job)
    monkeypatch.setattr(
        dashboard_app,
        "_read_job_result",
        lambda job_id: {
            "research_bundle": {
                "category": "황혼19금",
                "upload_title": "아내가 남긴 일기장 속에서 발견한 40년 전 첫사랑의 편지",
                "sources": [{"title": "source", "url": "https://example.com"}],
            }
        },
    )

    result = dashboard_app._submit_resume_job_from_pipeline(
        [
            {
                "job_id": "research-job",
                "job_type": "web_research",
                "status": "COMPLETED",
                "payload": {"topic_queue_id": "local-auto-1", "category": "황혼19금"},
            }
        ]
    )

    assert result == {
        "success": True,
        "job_id": "new-plan-job",
        "resumed_stage": "script_plan_generate",
    }
    assert submitted["job_type"] == "script_plan_generate"
    assert submitted["payload"]["topic_queue_id"] == "local-auto-1"
    assert submitted["payload"]["category"] == "황혼19금"
    assert submitted["payload"]["upload_title"] == "아내가 남긴 일기장 속에서 발견한 40년 전 첫사랑의 편지"
    assert submitted["payload"]["benchmark_analysis"]["web_research"]["sources"]
    assert submitted["payload"]["resume_from_job_id"] == "research-job"
