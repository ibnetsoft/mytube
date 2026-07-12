"""
[AIR-0227B Stage 4/5/6/8] Real Render Worker Process.

Replaces render_worker_mock.py as the process the Manager actually spawns
for render jobs (render_worker_mock.py is kept, unmodified, as an
AIR-0227A QA/reference artifact - not deleted per the task's own
minimal-invasiveness instruction).

Job source: worker/job_store.py (local SQLite), NOT the Supabase
remote_render_queue table remote_drive_worker.py used - that table access
went through service_role headers, which this process must never hold
(docs/AIR_WORKER_SECURITY.md §1). Only render_video is claimed; render_image/
render_audio are defined in the job schema but not implemented this Task
(docs/AIR_WORKER_JOB_PROTOCOL.md §1 lists them as future work).

Cancellation policy actually implemented here (docs/AIR_WORKER_JOB_RECOVERY.md
has the full rationale): a job can still be soft-cancelled (no process kill
needed) up through PREPARING - this worker checks its own cancel flag file
right before entering RENDERING. Once RENDERING has actually started,
remote_render_executor_func is a blocking call with no cancellation hook,
so a cancel request for that job is handled entirely by the Manager
(process-tree kill), not by this script.
"""
import signal
import sys
import time
from pathlib import Path

import job_store
import upload_adapter
from logging_setup import get_job_logger, get_logger
from render_pipeline_adapter import RenderPipelineError, cleanup_temp_dir, prepare_temp_dir, run_render
from shutdown_flag import is_shutdown_requested
from worker_config import CANCEL_FLAG_DIR, STATE_DIR

STATE_FILE = STATE_DIR / "render_worker.json"
DELIVERED_DIR = STATE_DIR / "delivered"
logger = get_logger("render_worker")

_shutdown_requested = False
SUPPORTED_JOB_TYPES = ["render_video"]


def _handle_signal(signum, frame):
    # [Windows caveat - see shutdown_flag.py] This only ever actually fires
    # for a real Ctrl+C in the same console; a Manager-issued
    # Popen.terminate() does NOT deliver SIGTERM on Windows. The file-flag
    # check in run_forever()'s loop condition is the real shutdown path.
    global _shutdown_requested
    logger.info(f"Received signal {signum}, requesting graceful shutdown (takes effect between jobs / at the PREPARING checkpoint only - see module docstring)")
    _shutdown_requested = True


def _should_stop() -> bool:
    return _shutdown_requested or is_shutdown_requested("render_worker")


def write_state(status: str, current_job: dict | None, progress: int, job_id: str | None = None):
    import json
    STATE_FILE.write_text(
        json.dumps(
            {
                "pid": None,  # filled in by the Manager from Popen, not self-reported
                "status": status,
                "current_job": current_job,
                "current_job_id": job_id,
                "progress": progress,
                "heartbeat_at": time.time(),
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


def _cancel_flag_path(job_id: str) -> Path:
    return CANCEL_FLAG_DIR / f"{job_id}.cancel"


def _is_soft_cancel_requested(job_id: str) -> bool:
    return _cancel_flag_path(job_id).exists()


def _clear_cancel_flag(job_id: str):
    _cancel_flag_path(job_id).unlink(missing_ok=True)


def _fail_and_maybe_retry(job: dict, error_code: str, error_message: str, job_log):
    job_id = job["job_id"]
    job_store.transition(job_id, job_store.FAILED, reason=error_message, error_code=error_code, error_message=error_message)
    job_log.error(f"FAILED: [{error_code}] {error_message}")
    refreshed = job_store.get_job(job_id)
    if refreshed["retry_count"] < refreshed["max_retries"]:
        job_store.transition(job_id, job_store.QUEUED, reason=f"auto-retry after failure ({refreshed['retry_count'] + 1}/{refreshed['max_retries']})")
        job_log.info(f"Re-queued for retry {refreshed['retry_count'] + 1}/{refreshed['max_retries']}")
    else:
        job_log.error(f"max_retries ({refreshed['max_retries']}) exhausted - job stays FAILED")


def process_one_job(job: dict, adapter: "upload_adapter.UploadAdapter", my_pid: int) -> None:
    job_id = job["job_id"]
    job_log = get_job_logger(job_id)
    job_log.info(f"Claimed by pid={my_pid}, payload={job['payload']}")
    logger.info(f"Claimed job {job_id}")

    temp_dir = None
    try:
        job_store.transition(job_id, job_store.PREPARING, reason="preparing render inputs")
        write_state("preparing", job, 0, job_id)
        job_log.info("-> PREPARING")

        source_path = job["payload"].get("source_path")
        if not source_path:
            raise RenderPipelineError("payload.source_path is required for render_video")
        temp_dir = prepare_temp_dir(source_path)
        job_log.info(f"Prepared temp_dir={temp_dir}")

        if _is_soft_cancel_requested(job_id):
            job_store.transition(job_id, job_store.CANCELED, reason="cancelled at PREPARING checkpoint (soft-cancel, no process kill needed)")
            job_log.info("-> CANCELED (soft-cancel at PREPARING checkpoint)")
            _clear_cancel_flag(job_id)
            return

        job_store.transition(job_id, job_store.RENDERING, reason="starting real render pipeline")
        write_state("rendering", job, 0, job_id)
        job_log.info("-> RENDERING (calling services.remote_render_service.remote_render_executor_func)")

        def _on_progress(pct, msg):
            job_store.update_progress(job_id, pct, msg)
            write_state("rendering", job, pct, job_id)
            job_log.info(f"progress={pct} message={msg}")

        output_path = run_render(job_id, temp_dir, _on_progress)
        job_log.info(f"Render complete: {output_path}")

        job_store.transition(job_id, job_store.UPLOADING, reason="render complete, delivering output")
        write_state("uploading", job, 100, job_id)
        job_log.info("-> UPLOADING")
        delivered_path = adapter.upload(output_path, job)
        job_log.info(f"Delivered to {delivered_path}")

        job_store.transition(job_id, job_store.COMPLETED, reason="delivered", output_path=delivered_path)
        job_log.info("-> COMPLETED")
        logger.info(f"Completed job {job_id} -> {delivered_path}")

    except job_store.InvalidTransitionError as e:
        # Someone else (Manager, cancel command) already moved this job out
        # from under us - not a render failure, just stop touching it.
        logger.warning(f"Job {job_id} state changed externally mid-run, aborting our own processing: {e}")
        job_log.warning(f"Aborted: externally transitioned ({e})")
    except Exception as e:
        _fail_and_maybe_retry(job, error_code="RENDER_EXCEPTION", error_message=str(e), job_log=job_log)
    finally:
        if temp_dir:
            cleanup_temp_dir(temp_dir)
        write_state("idle", None, 0)


def run_forever():
    from shutdown_flag import clear_shutdown_flag
    clear_shutdown_flag("render_worker")  # discard any stale flag from a previous instance of this process
    my_pid = __import__("os").getpid()
    logger.info(f"Render Worker (real pipeline) starting, pid={my_pid}")
    write_state("idle", None, 0)
    adapter = upload_adapter.LocalCopyUploadAdapter(DELIVERED_DIR)

    try:
        while not _should_stop():
            job = job_store.claim_next_job(SUPPORTED_JOB_TYPES, my_pid)
            if not job:
                write_state("idle", None, 0)
                time.sleep(1.0)
                continue
            process_one_job(job, adapter, my_pid)
    finally:
        write_state("stopped", None, 0)
        logger.info("Render Worker stopped")


def main():
    signal.signal(signal.SIGINT, _handle_signal)
    try:
        signal.signal(signal.SIGTERM, _handle_signal)
    except (AttributeError, ValueError):
        pass
    run_forever()


if __name__ == "__main__":
    if "--crash-now" in sys.argv:
        logger.info("--crash-now flag set, exiting with non-zero status immediately")
        sys.exit(1)
    main()
