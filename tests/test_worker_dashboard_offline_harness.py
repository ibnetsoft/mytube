import sys
from pathlib import Path

from fastapi.testclient import TestClient


ROOT = Path(__file__).resolve().parents[1]
WORKER_DIR = ROOT / "worker"
if str(WORKER_DIR) not in sys.path:
    sys.path.insert(0, str(WORKER_DIR))

import dashboard_app  # noqa: E402


def test_dashboard_offline_harness_endpoint_reports_pass():
    client = TestClient(dashboard_app.app)

    response = client.get("/api/autopilot/hermes/offline-harness?force=true")

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "pass"
    assert data["api_calls"] == 0
    assert data["failed_count"] == 0


def test_autopilot_start_blocks_before_worker_start_when_harness_fails(monkeypatch):
    def failing_harness(*, force=False):
        return {
            "status": "fail",
            "api_calls": 0,
            "check_count": 1,
            "failed_count": 1,
            "checks": [
                {
                    "name": "forced failure",
                    "passed": False,
                    "detail": "test preflight failure",
                    "category": "common",
                }
            ],
        }

    monkeypatch.setattr(dashboard_app, "_run_hermes_offline_harness", failing_harness)
    client = TestClient(dashboard_app.app)

    response = client.post("/api/autopilot/hermes/start", json={"settings": {"target_limit": 1}})

    assert response.status_code == 200
    data = response.json()
    assert data["success"] is False
    assert "offline preflight failed" in data["error"]
    assert data["offline_harness"]["failed_count"] == 1


def test_jobs_endpoint_includes_running_autopilot_internal_step(monkeypatch):
    monkeypatch.setattr(dashboard_app.job_store, "list_jobs", lambda status=None, limit=50: [])
    monkeypatch.setattr(
        dashboard_app.autopilot_manager,
        "get_status",
        lambda: {
            "is_running": True,
            "current_category": "황혼19금",
            "current_step": "신규 오리지널 영상 제목 생성",
            "last_error": "",
        },
    )
    client = TestClient(dashboard_app.app)

    response = client.get("/api/jobs?limit=10")

    assert response.status_code == 200
    jobs = response.json()["jobs"]
    assert jobs[0]["job_id"] == "hermes-autopilot-current"
    assert jobs[0]["job_type"] == "hermes_autopilot_step"
    assert jobs[0]["status"] == "RUNNING"
    assert jobs[0]["payload"]["current_step"] == "신규 오리지널 영상 제목 생성"
