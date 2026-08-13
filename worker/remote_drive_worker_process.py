"""AIRWorker-managed Google Drive API render queue process."""

import json
import os
import threading
import time

from logging_setup import get_logger
from shutdown_flag import clear_shutdown_flag, is_shutdown_requested
from worker_config import STATE_DIR, ensure_project_root_on_path

ensure_project_root_on_path()

from remote_drive_worker import RemoteDriveWorker  # noqa: E402

STATE_FILE = STATE_DIR / "remote_drive_worker.json"
logger = get_logger("remote_drive_worker")


def write_state(status: str, current_job: dict | None = None, progress: int = 0, last_error: str | None = None):
    prev = {}
    if STATE_FILE.exists():
        try:
            prev = json.loads(STATE_FILE.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            prev = {}

    STATE_FILE.write_text(
        json.dumps(
            {
                "pid": None,
                "status": status,
                "current_job": current_job,
                "current_job_id": current_job.get("id") if isinstance(current_job, dict) else None,
                "progress": progress,
                "heartbeat_at": time.time(),
                "last_success_at": prev.get("last_success_at"),
                "last_error": last_error if last_error is not None else prev.get("last_error"),
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


def _job_summary(job: dict) -> dict:
    return {
        "id": job.get("id"),
        "job_id": job.get("id"),
        "job_type": "drive_api_render",
        "project_id": job.get("project_id"),
        "project_name": job.get("project_name"),
        "asset_file_name": job.get("asset_file_name"),
    }


def main():
    clear_shutdown_flag("remote_drive_worker")
    logger.info("Remote Drive Worker process starting, pid=%s", os.getpid())
    write_state("starting")

    try:
        worker = RemoteDriveWorker()
    except Exception as exc:
        logger.exception("Remote Drive Worker failed to initialize")
        write_state("failed", last_error=str(exc))
        raise

    write_state("idle")
    while not is_shutdown_requested("remote_drive_worker"):
        try:
            job = worker.fetch_next_job()
            if not job:
                write_state("idle")
                time.sleep(worker.poll_interval)
                continue

            claimed = worker.claim_job(job)
            if not claimed:
                write_state("idle")
                continue

            summary = _job_summary(claimed)
            logger.info("Processing Drive API render job %s", claimed.get("id"))
            write_state("running", summary, int(claimed.get("progress") or 1))
            heartbeat_stop = threading.Event()

            def refresh_heartbeat():
                while not heartbeat_stop.wait(10):
                    try:
                        write_state("running", summary, int(claimed.get("progress") or 1))
                    except Exception:
                        logger.exception("Failed to refresh Remote Drive Worker heartbeat")

            heartbeat_thread = threading.Thread(
                target=refresh_heartbeat,
                name="remote-drive-heartbeat",
                daemon=True,
            )
            heartbeat_thread.start()
            try:
                worker.process_job(claimed)
            finally:
                heartbeat_stop.set()
                heartbeat_thread.join(timeout=2)

            state = json.loads(STATE_FILE.read_text(encoding="utf-8"))
            state["status"] = "idle"
            state["current_job"] = None
            state["current_job_id"] = None
            state["progress"] = 0
            state["heartbeat_at"] = time.time()
            state["last_success_at"] = time.time()
            state["last_error"] = None
            STATE_FILE.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")
        except Exception as exc:
            logger.exception("Remote Drive Worker tick failed")
            write_state("idle", last_error=str(exc))
            time.sleep(getattr(worker, "poll_interval", 10))

    write_state("stopped")
    logger.info("Remote Drive Worker process stopped")


if __name__ == "__main__":
    main()
