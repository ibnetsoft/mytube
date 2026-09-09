from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REMOTE_WORKER = (ROOT / "remote_drive_worker.py").read_text(encoding="utf-8")
PROCESS = (ROOT / "worker" / "remote_drive_worker_process.py").read_text(encoding="utf-8")


def test_remote_worker_process_refreshes_dashboard_progress_from_the_queue():
    assert "def get_job(self, job_id):" in REMOTE_WORKER
    assert '"select": "id,status,progress,message,error_message"' in REMOTE_WORKER
    assert 'latest_job = worker.get_job(claimed["id"]) or claimed' in PROCESS
    assert 'int(latest_job.get("progress") or 1)' in PROCESS
