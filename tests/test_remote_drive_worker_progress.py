from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REMOTE_WORKER = (ROOT / "remote_drive_worker.py").read_text(encoding="utf-8")
PROCESS = (ROOT / "worker" / "remote_drive_worker_process.py").read_text(encoding="utf-8")


def test_remote_worker_process_refreshes_dashboard_progress_from_the_queue():
    assert "def get_job(self, job_id):" in REMOTE_WORKER
    assert '"select": "id,status,progress,message,error_message"' in REMOTE_WORKER
    assert 'latest_job = worker.get_job(claimed["id"]) or claimed' in PROCESS
    assert 'int(latest_job.get("progress") or 1)' in PROCESS


def test_drive_renderer_reports_local_progress_file_back_to_the_remote_queue():
    assert "import threading" in REMOTE_WORKER
    assert 'progress_file = os.path.join(temp_dir, "progress.txt")' in REMOTE_WORKER
    assert "def sync_render_progress():" in REMOTE_WORKER
    assert "self.update_job(job_id, progress=progress, message=message)" in REMOTE_WORKER
    assert "progress_thread.join(timeout=3)" in REMOTE_WORKER


def test_drive_downloads_retry_then_fall_back_to_supabase_storage():
    assert 'REMOTE_RENDER_DRIVE_DOWNLOAD_ATTEMPTS", "3"' in REMOTE_WORKER
    assert "def _download_from_supabase_storage" in REMOTE_WORKER
    assert "def _download_asset_with_fallback" in REMOTE_WORKER
    assert 'storage_source=metadata.get("supabase_config")' in REMOTE_WORKER
    assert '"bucket": item.get("supabase_bucket")' in REMOTE_WORKER
