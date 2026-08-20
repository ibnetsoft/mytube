import pathlib
import sys


ROOT = pathlib.Path(__file__).resolve().parents[1]
WORKER = ROOT / "worker"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(WORKER) not in sys.path:
    sys.path.insert(0, str(WORKER))

from worker import dashboard_app


def test_hermes_process_card_uses_active_local_pipeline_job(monkeypatch):
    monkeypatch.setattr(
        dashboard_app,
        "_active_hermes_job_from_local_queue",
        lambda: {
            "job_id": "job-1",
            "job_type": "script_generate",
            "status": "RENDERING",
            "progress": 50,
            "progress_message": "writing script",
            "payload": {"upload_title": "버림받은 삼류무사가 사부의 검보를 펼친 날"},
        },
    )
    snap = {"processes": {"hermes_worker": {"status": "stopped", "pid": None}}}

    dashboard_app._sync_hermes_process_status(snap, {"is_running": False})

    hermes = snap["processes"]["hermes_worker"]
    assert hermes["status"] == "running"
    assert hermes["progress"] == 50
    assert hermes["current_job"]["job_id"] == "job-1"
    assert hermes["current_job"]["project_name"] == "버림받은 삼류무사가 사부의 검보를 펼친 날"


def test_hermes_process_card_uses_autopilot_when_no_active_job(monkeypatch):
    monkeypatch.setattr(dashboard_app, "_active_hermes_job_from_local_queue", lambda: None)
    snap = {"processes": {"hermes_worker": {"status": "stopped", "pid": None}}}

    dashboard_app._sync_hermes_process_status(snap, {"is_running": True, "current_step": "유튜브 탐색"})

    hermes = snap["processes"]["hermes_worker"]
    assert hermes["status"] == "running"
    assert hermes["current_job"] == "유튜브 탐색"
