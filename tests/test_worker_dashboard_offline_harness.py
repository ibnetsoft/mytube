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
