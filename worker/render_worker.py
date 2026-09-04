"""
[AIR-0227B Stage 4/5/6/8, AIR-0227C Stage 5/6/7] Real Render Worker Process.

Replaces render_worker_mock.py as the process the Manager actually spawns
for render jobs (render_worker_mock.py is kept, unmodified, as an
AIR-0227A QA/reference artifact - not deleted per the task's own
minimal-invasiveness instruction).

Two job sources, tried in this order each loop iteration:
  1. worker/job_store.py local queue (dev/test convenience - local
     `cli_status.py --submit-fixture`/`/jobs/submit`, unchanged since
     AIR-0227B, no service_role, no central server needed).
  2. Central server claim (AIR-0227C) via central_client.py, IF
     AIRWORKER_CENTRAL_SERVER_URL is configured - claims a lease-backed job
     and mirrors it into the local store (job_store.create_from_remote_claim)
     so it flows through the exact same state machine either way.

Only render_video is claimed; render_image/render_audio are defined in the
job schema but not implemented this Task.

Cancellation policy (docs/AIR_WORKER_JOB_RECOVERY.md has the full
rationale): a job can still be soft-cancelled (no process kill needed) up
through PREPARING - this worker checks its own cancel flag file right
before entering RENDERING. Once RENDERING has actually started,
remote_render_executor_func is a blocking call with no cancellation hook,
so a cancel request for that job is handled entirely by the Manager
(process-tree kill), not by this script.

Central server failure policy (AIR-0227C Stage 7,
docs/AIR_WORKER_REMOTE_E2E_QA.md has the live test results): claim/progress/
renew-lease failures are logged and treated as "nothing available this
tick" / best-effort - they never block or crash the render itself.
complete/fail reporting that ultimately fails after central_client's
retries is queued locally (job_store.mark_remote_ack_pending) and retried
at the top of every subsequent loop iteration until the server
acknowledges it - the local terminal status (COMPLETED/FAILED) is set
immediately regardless, so a network outage never causes a re-render of
already-finished work.
"""
import os
import signal
import sys
import threading
import time
import traceback
from pathlib import Path

import worker_config  # Load persisted settings before the central client snapshots credentials.
import central_client
import job_store
import upload_adapter
from logging_setup import get_job_logger, get_logger
from render_pipeline_adapter import RenderPipelineError, cleanup_temp_dir, prepare_temp_dir, run_render
from shutdown_flag import is_shutdown_requested
from worker_config import CANCEL_FLAG_DIR, OUTPUT_DIR, STATE_DIR, WORKER_ID, WORKER_INSTANCE_ID

STATE_FILE = STATE_DIR / "render_worker.json"
DELIVERED_DIR = OUTPUT_DIR / "delivered"  # [P2-VALIDATION] moved out of state/ into the canonical output/ subpath
logger = get_logger("render_worker")

_shutdown_requested = False
SUPPORTED_JOB_TYPES = ["render_video"]
LEASE_RENEW_INTERVAL_SECONDS = 3.0
REMOTE_ENABLED = bool(os.environ.get("AIRWORKER_CENTRAL_SERVER_URL"))
REMOTE_CLAIM_RETRY_SECONDS = 60.0
_next_remote_claim_at = 0.0


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


def _state_job_summary(current_job: dict | None) -> dict | None:
    if not isinstance(current_job, dict):
        return None
    payload = current_job.get("payload") if isinstance(current_job.get("payload"), dict) else {}
    project_name = (
        current_job.get("project_name")
        or payload.get("project_name")
        or payload.get("upload_title")
        or payload.get("topic")
        or payload.get("title")
    )
    return {
        "job_id": current_job.get("job_id"),
        "job_type": current_job.get("job_type"),
        "source": current_job.get("source"),
        "status": current_job.get("status"),
        "project_name": project_name,
        "progress_message": current_job.get("progress_message"),
    }


def write_state(status: str, current_job: dict | None, progress: int, job_id: str | None = None,
                 last_success_at: float | None = None, last_error: str | None = None):
    import json
    prev = {}
    if STATE_FILE.exists():
        try:
            prev = json.loads(STATE_FILE.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            prev = {}
    STATE_FILE.write_text(
        json.dumps(
            {
                "pid": None,  # filled in by the Manager from Popen, not self-reported
                "status": status,
                "current_job": _state_job_summary(current_job),
                "current_job_id": job_id,
                "progress": progress,
                "worker_instance_id": WORKER_INSTANCE_ID,
                "heartbeat_at": time.time(),
                # [AIR-0227E-P3 item 11] mirrors hermes_worker.py's state
                # shape so Local API /status can show both workers'
                # last-success/last-error uniformly - additive fields only,
                # existing consumers of this file ignore unknown keys.
                "last_success_at": last_success_at if last_success_at is not None else prev.get("last_success_at"),
                "last_error": last_error if last_error is not None else prev.get("last_error"),
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
    """Local auto-retry only applies to locally-sourced jobs (max_retries>0).
    Remote (central_server) jobs are created with max_retries=0
    (job_store.create_from_remote_claim) - retry ownership for those belongs
    to the central server (principle #3), not this worker; see
    _report_remote_outcome's fail_job call below."""
    job_id = job["job_id"]
    job_store.transition(job_id, job_store.FAILED, reason=error_message, error_code=error_code, error_message=error_message)
    job_log.error(f"FAILED: [{error_code}] {error_message}")
    refreshed = job_store.get_job(job_id)
    if refreshed["retry_count"] < refreshed["max_retries"]:
        job_store.transition(job_id, job_store.QUEUED, reason=f"auto-retry after failure ({refreshed['retry_count'] + 1}/{refreshed['max_retries']})")
        job_log.info(f"Re-queued for retry {refreshed['retry_count'] + 1}/{refreshed['max_retries']}")
    else:
        job_log.info(f"No further local auto-retry (retry_count={refreshed['retry_count']}, max_retries={refreshed['max_retries']}) - job stays FAILED" +
                      (" (remote job - central server owns retry decisions)" if refreshed["source"] == "central_server" else ""))


def _is_remote(job: dict) -> bool:
    return job.get("source") == "central_server" and job.get("remote_job_id")


def _start_lease_renewal(job: dict, job_log) -> tuple[threading.Thread, threading.Event] | tuple[None, None]:
    if not _is_remote(job):
        return None, None
    stop_event = threading.Event()

    def _loop():
        while not stop_event.wait(LEASE_RENEW_INTERVAL_SECONDS):
            try:
                result = central_client.renew_lease(job["remote_job_id"], job["lease_id"], WORKER_INSTANCE_ID)
                job_store.update_lease(job["job_id"], result["lease_expires_at"])
                job_log.info(f"Lease renewed, expires_at={result['lease_expires_at']:.1f}")
            except Exception as e:
                job_log.warning(f"Lease renewal failed (non-fatal, will retry next interval): {e}")

    t = threading.Thread(target=_loop, daemon=True, name=f"lease-renew-{job['job_id']}")
    t.start()
    return t, stop_event


def _report_remote_outcome(job: dict, job_log, *, success: bool, output_ref: str = "", error_code: str = "", error_message: str = ""):
    """[Bug found via live network-failure QA, fixed here] This must NEVER
    let an exception escape - it is called right after the local job_store
    transition to COMPLETED/FAILED has already committed. The first version
    only caught (CentralServerUnavailable, AuthError); a real run against a
    genuinely unreachable/inconsistent central server produced an
    unexpected HTTP 409 (requests.exceptions.HTTPError, not one of those
    two types), which propagated out of this function, was caught by
    process_one_job's outer `except Exception`, and THAT handler tried to
    transition the (already-COMPLETED) job to FAILED - an invalid
    transition that raised InvalidTransitionError uncaught, which crashed
    the whole Render Worker process. The fix is structural, not just
    'catch one more exception type': reporting to the central server must
    be fully isolated from the local state machine's own error handling,
    since a remote-reporting failure is never a reason to alter a local
    outcome that already succeeded/failed on its own terms."""
    if not _is_remote(job):
        return
    idem_key = job["job_id"]  # local job_id is stable and unique per attempt - safe as the idempotency key
    try:
        if success:
            central_client.complete_job(job["remote_job_id"], job["lease_id"], WORKER_INSTANCE_ID, idem_key, output_ref)
        else:
            central_client.fail_job(job["remote_job_id"], job["lease_id"], WORKER_INSTANCE_ID, idem_key, error_code, error_message)
        job_store.mark_remote_acked(job["job_id"])
        job_log.info(f"Central server acknowledged {'completion' if success else 'failure'}")
    except central_client.LeaseConflict as e:
        # [Found via a live long-outage test] retrying a 409 will NEVER
        # succeed (the lease this report refers to is already resolved on
        # the server, one way or another) - stop retrying instead of
        # leaving it 'pending' forever. Does not by itself prevent this
        # worker having *also* independently re-claimed and re-rendered
        # the same job after its expired lease was swept during the same
        # outage - see docs/AIR_WORKER_REMOTE_E2E_QA.md for the documented
        # known limitation and why fully closing it is out of this Task's
        # remaining scope.
        try:
            job_store.mark_remote_ack_abandoned(job["job_id"])
        except Exception:
            pass
        job_log.warning(f"Central server rejected this {'completion' if success else 'failure'} report as stale (lease no longer active) - giving up on this report, NOT retrying: {e}")
    except Exception as e:
        # Deliberately broad: ANY other failure to reach/satisfy the central
        # server (network, auth, unexpected 5xx, malformed response) must
        # be non-fatal to the already-decided local outcome, and IS worth
        # retrying later (transient).
        try:
            job_store.mark_remote_ack_pending(job["job_id"])
        except Exception:
            pass  # even the local bookkeeping update must not be allowed to crash this path
        job_log.warning(f"Could not report {'completion' if success else 'failure'} to central server ({e}) - queued for retry, local status is final regardless")


def _remote_progress(job: dict, job_log, worker_status: str, progress: int, message: str):
    if not _is_remote(job):
        return
    try:
        central_client.report_progress(job["remote_job_id"], job["lease_id"], WORKER_INSTANCE_ID, progress, message, worker_status)
    except Exception as e:
        job_log.warning(f"Progress report to central server failed (non-fatal): {e}")


def _format_exception_detail(exc: Exception) -> str:
    return "\n".join(
        [
            f"Exception: {type(exc).__name__}: {exc}",
            "Traceback:",
            traceback.format_exc(),
        ]
    ).strip()


def _flush_pending_remote_acks():
    """[Stage 7] Retries reporting outcomes that failed to reach the central
    server earlier - runs once per main-loop iteration so a temporary
    outage self-heals without operator intervention."""
    for job in job_store.list_pending_remote_acks():
        job_log = get_job_logger(job["job_id"])
        if job["status"] == job_store.COMPLETED:
            _report_remote_outcome(job, job_log, success=True, output_ref=job.get("output_path") or "")
        else:
            _report_remote_outcome(job, job_log, success=False, error_code=job.get("error_code") or "", error_message=job.get("error_message") or "")


def process_one_job(job: dict, adapter: "upload_adapter.UploadAdapter") -> None:
    job_id = job["job_id"]
    job_log = get_job_logger(job_id)
    job_log.info(f"Claimed (source={job['source']}, remote_job_id={job.get('remote_job_id')}), payload={job['payload']}")
    logger.info(f"Claimed job {job_id}")

    renew_thread, renew_stop = _start_lease_renewal(job, job_log)
    temp_dir = None
    _last_success_at = None
    _last_error = None
    try:
        job_store.transition(job_id, job_store.PREPARING, reason="preparing render inputs")
        write_state("preparing", job, 0, job_id)
        _remote_progress(job, job_log, "PREPARING", 1, "Preparing render inputs.")
        job_log.info("-> PREPARING")

        if job["job_type"] != "render_video":
            raise RenderPipelineError(f"unsupported render job_type: {job['job_type']}")
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

        def _on_progress(pct, msg):
            job_store.update_progress(job_id, pct, msg)
            write_state("rendering", job, pct, job_id)
            job_log.info(f"progress={pct} message={msg}")
            _remote_progress(job, job_log, "RENDERING", pct, msg)

        _remote_progress(job, job_log, "RENDERING", 20, "Rendering video on remote worker.")
        job_log.info("-> RENDERING (calling services.remote_render_service.remote_render_executor_func)")
        output_path = run_render(job_id, temp_dir, _on_progress)
        job_log.info(f"Render complete: {output_path}")

        job_store.transition(job_id, job_store.UPLOADING, reason="render complete, delivering output")
        write_state("uploading", job, 100, job_id)
        _remote_progress(job, job_log, "UPLOADING", 92, "Uploading rendered video.")
        job_log.info("-> UPLOADING")
        delivered_path = adapter.upload(output_path, job)
        job_log.info(f"Delivered to {delivered_path}")

        job_store.transition(job_id, job_store.COMPLETED, reason="delivered", output_path=delivered_path)
        job_log.info("-> COMPLETED")
        logger.info(f"Completed job {job_id} -> {delivered_path}")
        _report_remote_outcome(job, job_log, success=True, output_ref=delivered_path)
        _last_success_at = time.time()

    except job_store.InvalidTransitionError as e:
        # Someone else (Manager, cancel command) already moved this job out
        # from under us - not a render failure, just stop touching it.
        logger.warning(f"Job {job_id} state changed externally mid-run, aborting our own processing: {e}")
        job_log.warning(f"Aborted: externally transitioned ({e})")
    except Exception as e:
        error_detail = _format_exception_detail(e)
        _fail_and_maybe_retry(job, error_code="RENDER_EXCEPTION", error_message=error_detail, job_log=job_log)
        _report_remote_outcome(job, job_log, success=False, error_code="RENDER_EXCEPTION", error_message=error_detail)
        _last_error = error_detail
    finally:
        if renew_stop:
            renew_stop.set()
        if temp_dir:
            cleanup_temp_dir(temp_dir)
        write_state("idle", None, 0, last_success_at=_last_success_at, last_error=_last_error)


def _try_remote_claim() -> dict | None:
    global _next_remote_claim_at
    now = time.time()
    if now < _next_remote_claim_at:
        return None
    try:
        claimed = central_client.claim_job(WORKER_ID, WORKER_INSTANCE_ID, SUPPORTED_JOB_TYPES)
    except central_client.AuthError as e:
        logger.error(f"Central server rejected our worker token (not retrying this tick): {e}")
        _next_remote_claim_at = now + REMOTE_CLAIM_RETRY_SECONDS
        return None
    except central_client.CentralServerUnavailable as e:
        logger.warning(f"Central server unreachable (will retry after {REMOTE_CLAIM_RETRY_SECONDS:.0f}s): {e}")
        _next_remote_claim_at = now + REMOTE_CLAIM_RETRY_SECONDS
        return None
    except Exception as e:
        # [Same class of bug as _report_remote_outcome, hardened proactively]
        # any other unexpected response (malformed claim, unexpected 4xx)
        # must not crash the main loop - just skip this tick's remote claim.
        logger.error(f"Unexpected error during central server claim (will retry after {REMOTE_CLAIM_RETRY_SECONDS:.0f}s): {e}")
        _next_remote_claim_at = now + REMOTE_CLAIM_RETRY_SECONDS
        return None
    if not claimed:
        return None
    local_job_id = job_store.create_from_remote_claim(
        remote_job_id=claimed["job_id"], job_type=claimed["job_type"], payload=claimed["payload"],
        priority=claimed["priority"], lease_id=claimed["lease_id"], worker_instance_id=WORKER_INSTANCE_ID,
        lease_expires_at=claimed["lease_expires_at"],
    )
    return job_store.get_job(local_job_id)


def run_forever():
    from shutdown_flag import clear_shutdown_flag
    clear_shutdown_flag("render_worker")  # discard any stale flag from a previous instance of this process
    logger.info(f"Render Worker (real pipeline) starting, pid={os.getpid()}, worker_instance_id={WORKER_INSTANCE_ID}, remote_enabled={REMOTE_ENABLED}")
    write_state("idle", None, 0)
    adapter = upload_adapter.LocalCopyUploadAdapter(DELIVERED_DIR)

    try:
        while not _should_stop():
            try:
                _flush_pending_remote_acks()

                job = job_store.claim_next_job(SUPPORTED_JOB_TYPES, os.getpid())
                if not job and REMOTE_ENABLED:
                    job = _try_remote_claim()
                if not job:
                    write_state("idle", None, 0)
                    time.sleep(1.0)
                    continue
                process_one_job(job, adapter)
            except Exception as e:
                # [Defense in depth after the 409-crash bug found via live
                # QA] process_one_job/central_client calls are already
                # hardened individually, but this outer per-iteration catch
                # (mirroring manager.py's supervisor loop pattern) is the
                # last line of defense against any remaining unexpected
                # exception - a local SQLite hiccup, a bug in a code path
                # not yet exercised by QA, etc. - so the whole process
                # never dies from something that should just be logged and
                # retried on the next tick.
                logger.error(f"Unexpected error in main loop iteration (non-fatal, continuing): {e}")
                write_state("idle", None, 0)
                time.sleep(1.0)
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
