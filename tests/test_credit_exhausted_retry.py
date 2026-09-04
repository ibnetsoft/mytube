import pathlib
import sys

import pytest


ROOT = pathlib.Path(__file__).resolve().parents[1]
WORKER = ROOT / "worker"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(WORKER) not in sys.path:
    sys.path.insert(0, str(WORKER))

import job_store
from worker import dashboard_app


def test_credit_exhausted_job_requeues_only_after_explicit_manual_action(monkeypatch):
    job = {
        "job_id": "credit-job",
        "source": "dashboard",
        "remote_job_id": None,
        "status": job_store.FAILED,
        "error_code": job_store.CREDIT_EXHAUSTED_ERROR_CODE,
    }
    captured = {}

    monkeypatch.setattr(job_store, "get_job", lambda job_id: job if job_id == "credit-job" else None)

    def fake_transition(job_id, status, **kwargs):
        captured.update(job_id=job_id, status=status, **kwargs)
        return {"job_id": job_id, "status": status}

    monkeypatch.setattr(job_store, "transition", fake_transition)

    assert job_store.retry_after_credit_recharge("credit-job") == {"job_id": "credit-job", "status": "QUEUED"}
    assert captured["status"] == job_store.QUEUED
    assert captured["error_code"] == ""
    assert captured["error_message"] == ""
    assert captured["progress"] == 0


def test_manual_retry_rejects_non_credit_failure(monkeypatch):
    monkeypatch.setattr(job_store, "get_job", lambda _job_id: {
        "job_id": "ordinary-failure",
        "source": "dashboard",
        "remote_job_id": None,
        "status": job_store.FAILED,
        "error_code": "HERMES_EXCEPTION",
    })

    with pytest.raises(ValueError, match="크레딧 소진"):
        job_store.retry_after_credit_recharge("ordinary-failure")


def test_regeneration_required_job_requeues_only_after_explicit_manual_action(monkeypatch):
    job = {
        "job_id": "regen-job",
        "source": "dashboard",
        "remote_job_id": None,
        "status": job_store.FAILED,
        "error_code": job_store.REGEN_REQUIRED_ERROR_CODE,
    }
    captured = {}
    monkeypatch.setattr(job_store, "get_job", lambda job_id: job if job_id == "regen-job" else None)

    def fake_transition(job_id, status, **kwargs):
        captured.update(job_id=job_id, status=status, **kwargs)
        return {"job_id": job_id, "status": status}

    monkeypatch.setattr(job_store, "transition", fake_transition)

    assert job_store.retry_after_regeneration_required("regen-job") == {"job_id": "regen-job", "status": "QUEUED"}
    assert captured["status"] == job_store.QUEUED
    assert captured["progress"] == 0
    assert captured["progress_message"] == "현재 제목·구조 유지, 수동 재생성 대기"


def test_dashboard_retry_endpoint_uses_credit_recharge_requeue(monkeypatch):
    monkeypatch.setattr(dashboard_app, "require_auth", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        dashboard_app.job_store,
        "retry_after_credit_recharge",
        lambda job_id: {"job_id": job_id, "status": "QUEUED"},
    )

    result = dashboard_app.api_retry_credit_exhausted_job("credit-job")

    assert result == {"success": True, "job": {"job_id": "credit-job", "status": "QUEUED"}}


def test_dashboard_exposes_credit_recharge_button_only_for_credit_failures():
    source = (ROOT / "worker" / "dashboard_app.py").read_text(encoding="utf-8")

    assert "/api/jobs/${jobId}/retry-credit-exhausted" in source
    assert "충전 후 재실행" in source
    assert "function canRetryCreditExhausted(job)" in source
