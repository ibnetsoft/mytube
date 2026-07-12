"""
[AIR-0227A Stage 12] Mock Render Worker Process.

Standalone entry point (run as its own OS process via subprocess.Popen from
manager.py) - simulates picking up render_image/render_video/render_audio
jobs and "rendering" them (sleep, no real ffmpeg/MoviePy call - the real
pipeline connection is explicitly out of scope for this Task, per
docs/AIR_WORKER_ARCHITECTURE.md §0 and the task's own prohibition list).

Writes its own heartbeat/status file (state/render_worker.json) that the
Worker Manager polls - this is the IPC mechanism between the Manager and
this separate OS process (no shared memory, no message queue needed for
the skeleton).
"""
import json
import signal
import sys
import time
from pathlib import Path

from worker_config import STATE_DIR
from logging_setup import get_logger

STATE_FILE = STATE_DIR / "render_worker.json"
logger = get_logger("render_worker")

_shutdown_requested = False


def _handle_signal(signum, frame):
    global _shutdown_requested
    logger.info(f"Received signal {signum}, requesting graceful shutdown")
    _shutdown_requested = True


def write_state(status: str, current_job: dict | None, progress: int):
    STATE_FILE.write_text(
        json.dumps(
            {
                "pid": None,  # filled in by the Manager from Popen, not self-reported
                "status": status,
                "current_job": current_job,
                "progress": progress,
                "heartbeat_at": time.time(),
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


def fake_job_source():
    """[AIR-0227A skeleton] Stands in for the central-server job feed
    (docs/AIR_WORKER_JOB_PROTOCOL.md §3: real job source stays server-side,
    this Task uses a local mock generator only).

    Produces a finite burst of jobs then goes idle for a while before the
    next burst - a real, continuous job source is unrealistic for this
    skeleton and would make the "Hermes resumes once the render queue is
    empty" QA scenario (docs/AIR_WORKER_RESOURCE_POLICY.md §3) untestable,
    since Hermes would never see an idle window."""
    batch = 0
    while True:
        batch += 1
        for n in range(1, 4):  # 3-job burst
            yield {
                "job_id": f"mock-render-b{batch}-{n}",
                "job_type": "render_video",
                "priority": 100,
                "payload": {"project_id": 9000 + n},
            }
        write_state("idle", None, 0)
        logger.info("Render queue empty - idling before next burst")
        time.sleep(20)


def main():
    signal.signal(signal.SIGINT, _handle_signal)
    try:
        signal.signal(signal.SIGTERM, _handle_signal)
    except (AttributeError, ValueError):
        pass  # SIGTERM not available on this platform/thread context

    logger.info("Render Worker (mock) starting")
    write_state("running", None, 0)

    jobs = fake_job_source()
    try:
        for job in jobs:
            if _shutdown_requested:
                break
            logger.info(f"Picked up job {job['job_id']}")
            for pct in (0, 25, 50, 75, 100):
                if _shutdown_requested:
                    logger.info(f"Shutdown requested mid-job {job['job_id']}, stopping cleanly")
                    break
                write_state("running", job, pct)
                time.sleep(1)
            if not _shutdown_requested:
                logger.info(f"Completed job {job['job_id']}")
            time.sleep(1)
    finally:
        write_state("stopped", None, 0)
        logger.info("Render Worker (mock) stopped")


if __name__ == "__main__":
    if "--crash-now" in sys.argv:
        # QA hook: docs/AIR_WORKER_PROCESS_MODEL.md §3 crash-handling tests
        # need a deterministic way to make this process die immediately.
        logger.info("--crash-now flag set, exiting with non-zero status immediately")
        sys.exit(1)
    main()
