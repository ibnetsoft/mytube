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
from services.remote_publish_service import RemotePublishService  # noqa: E402

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
                "pid": os.getpid(),
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
        "progress_message": job.get("message") or "",
    }


def _publish_job_summary(request: dict) -> dict:
    metadata = request.get("metadata") or {}
    operation = metadata.get("publish_operation") or "upload"
    return {
        "id": request.get("id"),
        "job_id": request.get("id"),
        "job_type": "youtube_release" if operation == "release" else "youtube_publish",
        "project_id": metadata.get("project_id"),
        "project_name": metadata.get("title") or metadata.get("project_name"),
        "asset_file_name": metadata.get("drive_video_file_name"),
        "progress_message": "YouTube 공개 전환 중..." if operation == "release" else "YouTube 비공개 업로드 준비 중...",
    }


def _mark_idle_success():
    state = json.loads(STATE_FILE.read_text(encoding="utf-8"))
    state["status"] = "idle"
    state["current_job"] = None
    state["current_job_id"] = None
    state["progress"] = 0
    state["heartbeat_at"] = time.time()
    state["last_success_at"] = time.time()
    state["last_error"] = None
    STATE_FILE.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")


def main():
    clear_shutdown_flag("remote_drive_worker")
    logger.info("Remote Drive Worker process starting, pid=%s", os.getpid())
    write_state("starting")

    try:
        worker = RemoteDriveWorker()
        publisher = RemotePublishService(worker.worker_id)
    except Exception as exc:
        logger.exception("Remote Drive Worker failed to initialize")
        write_state("failed", last_error=str(exc))
        raise

    write_state("idle", last_error="")
    while not is_shutdown_requested("remote_drive_worker"):
        try:
            job = worker.fetch_next_job()
            if not job:
                publish_request = publisher.fetch_next_request()
                if publish_request:
                    claimed_publish = publisher.claim_request(publish_request)
                    if claimed_publish:
                        summary = _publish_job_summary(claimed_publish)
                        publish_progress = {"value": 1, "message": summary["progress_message"]}
                        write_state("running", summary, publish_progress["value"])
                        heartbeat_stop = threading.Event()

                        def update_publish_progress(progress: int, message: str):
                            publish_progress["value"] = progress
                            publish_progress["message"] = message

                        def refresh_publish_heartbeat():
                            while not heartbeat_stop.wait(10):
                                latest_summary = {**summary, "progress_message": publish_progress["message"]}
                                write_state("running", latest_summary, publish_progress["value"])

                        heartbeat_thread = threading.Thread(
                            target=refresh_publish_heartbeat,
                            name="remote-publish-heartbeat",
                            daemon=True,
                        )
                        heartbeat_thread.start()
                        try:
                            publisher.process_claimed_request(claimed_publish, update_publish_progress)
                        finally:
                            heartbeat_stop.set()
                            heartbeat_thread.join(timeout=2)
                        _mark_idle_success()
                        continue
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
                        latest_job = worker.get_job(claimed["id"]) or claimed
                        latest_summary = {**summary, "progress_message": latest_job.get("message") or ""}
                        write_state(
                            "running",
                            latest_summary,
                            int(latest_job.get("progress") or 1),
                            latest_job.get("error_message") or None,
                        )
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

            _mark_idle_success()
        except Exception as exc:
            logger.exception("Remote Drive Worker tick failed")
            write_state("idle", last_error=str(exc))
            time.sleep(getattr(worker, "poll_interval", 10))

    write_state("stopped")
    logger.info("Remote Drive Worker process stopped")


if __name__ == "__main__":
    main()
