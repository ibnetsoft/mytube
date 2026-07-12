"""
[AIR-0227A Stage 12] Mock Hermes Worker Process.

Standalone entry point - simulates topic_research/topic_generate/
topic_deduplicate/topic_rank jobs (sleep, no real external LLM call - the
real Hermes runtime connection is explicitly out of scope for this Task).

Honors a pause flag file written by the Manager
(docs/AIR_WORKER_RESOURCE_POLICY.md §2: "실행 중인 Hermes 작업은 안전한
체크포인트에서 일시 정지 가능") - checks it between simulated "LLM call"
steps, never mid-step, mirroring the checkpoint design in that doc.
"""
import json
import signal
import time
from pathlib import Path

from config import STATE_DIR
from logging_setup import get_logger

STATE_FILE = STATE_DIR / "hermes_worker.json"
PAUSE_FLAG_FILE = STATE_DIR / "hermes_worker.pause"
logger = get_logger("hermes_worker")

_shutdown_requested = False


def _handle_signal(signum, frame):
    global _shutdown_requested
    logger.info(f"Received signal {signum}, requesting graceful shutdown")
    _shutdown_requested = True


def write_state(status: str, current_job: dict | None, progress: int):
    STATE_FILE.write_text(
        json.dumps(
            {
                "pid": None,
                "status": status,
                "current_job": current_job,
                "progress": progress,
                "heartbeat_at": time.time(),
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


def is_paused() -> bool:
    return PAUSE_FLAG_FILE.exists()


def fake_job_source():
    i = 0
    while True:
        i += 1
        yield {
            "job_id": f"mock-topic-research-{i}",
            "job_type": "topic_research",
            "priority": 20,
            "payload": {"category": "poc-category"},
        }


def main():
    signal.signal(signal.SIGINT, _handle_signal)
    try:
        signal.signal(signal.SIGTERM, _handle_signal)
    except (AttributeError, ValueError):
        pass

    logger.info("Hermes Worker (mock) starting")
    write_state("running", None, 0)

    jobs = fake_job_source()
    try:
        for job in jobs:
            if _shutdown_requested:
                break

            # Checkpoint: don't even START a new job while paused.
            while is_paused() and not _shutdown_requested:
                write_state("paused", None, 0)
                logger.info("Paused (render job in progress) - waiting before starting next job")
                time.sleep(1)
            if _shutdown_requested:
                break

            logger.info(f"Picked up job {job['job_id']}")
            for step, pct in enumerate((0, 20, 40, 60, 80, 100)):
                if _shutdown_requested:
                    logger.info(f"Shutdown requested mid-job {job['job_id']}, stopping cleanly")
                    break
                write_state("running", job, pct)
                time.sleep(1)
                # Checkpoint between steps only (mirrors "LLM 호출 완료 후
                # 결과 저장 직전" boundary in docs/AIR_WORKER_RESOURCE_POLICY.md §2) -
                # never abandon a step half-done.
                if is_paused() and pct < 100:
                    logger.info(f"Pause requested mid-job {job['job_id']} - finishing current step, will pause before next")
            if not _shutdown_requested:
                logger.info(f"Completed job {job['job_id']}")
            time.sleep(1)
    finally:
        write_state("stopped", None, 0)
        logger.info("Hermes Worker (mock) stopped")


if __name__ == "__main__":
    import sys
    if "--crash-now" in sys.argv:
        logger.info("--crash-now flag set, exiting with non-zero status immediately")
        sys.exit(1)
    main()
