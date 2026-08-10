"""
[AIR-0227B Stage 2 / AIR-0227C Stage 3] Local API - genuinely separate OS
process, loopback-only (docs/AIR_WORKER_SECURITY.md §2).

[AIR-0227C Stage 3] Auth policy (docs/AIR_WORKER_LOCAL_API_SECURITY.md has
the full writeup): only /health is unauthenticated. Every other endpoint -
including read-only ones like /status and /jobs, since job payloads and
(from AIR-0227C on) lease/worker-instance data are not meant to be
world-readable on the loopback interface - requires
`Authorization: Bearer <token>` verified against the DPAPI-protected local
token store (local_api_token.py). Token is never accepted via query string
or CLI argument. Destructive endpoints additionally get an audit log line
(token itself never logged).
"""
import json
import time
from pathlib import Path

import job_store
from fastapi import FastAPI, Header, HTTPException
from ipc import submit_command, wait_for_result
from local_api_token import verify_token
from logging_setup import get_logger
from render_pipeline_adapter import render_status_display
from worker_config import LOG_FILES, STATE_DIR, WORKER_ID

logger = get_logger("local_api")
audit_logger = get_logger("local_api")  # same file - [AUDIT] prefix distinguishes entries, no new log file needed

app = FastAPI(title="AIR Worker Local API")

MANAGER_STATUS_FILE = STATE_DIR / "manager_status.json"


def require_auth(authorization: str | None = Header(default=None)):
    """FastAPI dependency - raises 401 for both 'missing' and 'invalid' so
    the response doesn't distinguish the two cases (docs/AIR_WORKER_LOCAL_API_SECURITY.md
    §policy). Never logs the header value itself."""
    token = None
    if authorization and authorization.startswith("Bearer "):
        token = authorization[len("Bearer "):]
    if not verify_token(token):
        logger.warning("Local API auth failed (missing or invalid token) - request rejected")
        raise HTTPException(status_code=401, detail="Missing or invalid Authorization token")


def audit(action: str, detail: str = ""):
    audit_logger.warning(f"[AUDIT] {action} {detail}".strip())


def _read_manager_status() -> dict:
    if not MANAGER_STATUS_FILE.exists():
        return {"processes": {}, "hermes_paused": False, "worker_id": WORKER_ID, "manager_alive": False}
    try:
        data = json.loads(MANAGER_STATUS_FILE.read_text(encoding="utf-8"))
        data["manager_alive"] = (time.time() - data.get("written_at", 0)) < 5
        return data
    except (json.JSONDecodeError, OSError):
        return {"processes": {}, "hermes_paused": False, "worker_id": WORKER_ID, "manager_alive": False}


@app.get("/health")
async def health():
    return {"status": "ok", "time": time.time()}


@app.get("/status")
async def status(authorization: str | None = Header(default=None)):
    require_auth(authorization)
    snap = _read_manager_status()
    snap["render_status"] = render_status_display()
    return snap


@app.get("/processes")
async def processes(authorization: str | None = Header(default=None)):
    require_auth(authorization)
    return _read_manager_status().get("processes", {})


@app.post("/processes/render/start")
async def render_start(authorization: str | None = Header(default=None)):
    require_auth(authorization)
    audit("processes/render/start")
    return wait_for_result(submit_command("start_process", {"name": "render_worker"}))


@app.post("/processes/render/stop")
async def render_stop(authorization: str | None = Header(default=None)):
    require_auth(authorization)
    audit("processes/render/stop")
    return wait_for_result(submit_command("stop_process", {"name": "render_worker"}))


@app.post("/processes/remote-drive/start")
async def remote_drive_start(authorization: str | None = Header(default=None)):
    require_auth(authorization)
    audit("processes/remote-drive/start")
    return wait_for_result(submit_command("start_process", {"name": "remote_drive_worker"}))


@app.post("/processes/remote-drive/stop")
async def remote_drive_stop(authorization: str | None = Header(default=None)):
    require_auth(authorization)
    audit("processes/remote-drive/stop")
    return wait_for_result(submit_command("stop_process", {"name": "remote_drive_worker"}))


@app.post("/processes/hermes/start")
async def hermes_start(authorization: str | None = Header(default=None)):
    require_auth(authorization)
    audit("processes/hermes/start")
    return wait_for_result(submit_command("start_process", {"name": "hermes_worker"}))


@app.post("/processes/hermes/stop")
async def hermes_stop(authorization: str | None = Header(default=None)):
    require_auth(authorization)
    audit("processes/hermes/stop")
    return wait_for_result(submit_command("stop_process", {"name": "hermes_worker"}))


@app.get("/jobs")
async def jobs(status: str | None = None, limit: int = 50, authorization: str | None = Header(default=None)):
    require_auth(authorization)
    return {"jobs": job_store.list_jobs(status=status, limit=limit)}


@app.get("/jobs/{job_id}")
async def job_detail(job_id: str, authorization: str | None = Header(default=None)):
    require_auth(authorization)
    job = job_store.get_job(job_id)
    if not job:
        return {"error": "not found"}
    job["transitions"] = job_store.transition_history(job_id)
    return job


@app.post("/jobs/submit")
async def submit_job(body: dict, authorization: str | None = Header(default=None)):
    require_auth(authorization)
    job_id = job_store.submit_job(
        job_type=body.get("job_type", "render_video"),
        payload=body.get("payload", {}),
        priority=body.get("priority", 100),
        source=body.get("source", "local_api"),
        max_retries=body.get("max_retries", 3),
    )
    audit("jobs/submit", f"job_id={job_id} job_type={body.get('job_type', 'render_video')}")
    return {"job_id": job_id}


@app.post("/jobs/{job_id}/cancel")
async def cancel_job(job_id: str, authorization: str | None = Header(default=None)):
    """docs/AIR_WORKER_JOB_RECOVERY.md cancellation policy: QUEUED/CLAIMED/
    PREPARING can be cancelled without killing any process; RENDERING/
    UPLOADING require the Manager to process-tree-kill the Render Worker -
    submitted as a command either way since only the Manager can safely
    decide + execute which path applies (it knows the live process pid)."""
    require_auth(authorization)
    audit("jobs/cancel", f"job_id={job_id}")
    return wait_for_result(submit_command("cancel_job", {"job_id": job_id}), timeout=15)


@app.get("/logs")
async def logs(process: str = "manager", tail_lines: int = 50, authorization: str | None = Header(default=None)):
    require_auth(authorization)
    path = LOG_FILES.get(process)
    if not path or not Path(path).exists():
        return {"error": f"Unknown or empty log for process '{process}'", "available": list(LOG_FILES.keys())}
    lines = Path(path).read_text(encoding="utf-8", errors="replace").splitlines()
    return {"process": process, "lines": lines[-tail_lines:]}


@app.post("/_test/crash-local-api")
async def test_crash_local_api(authorization: str | None = Header(default=None)):
    """[QA hook only] Simulates this whole process dying, to verify the
    Manager auto-restarts it."""
    require_auth(authorization)
    audit("_test/crash-local-api")
    import os
    import threading

    def _die():
        time.sleep(0.2)
        os._exit(1)

    threading.Thread(target=_die, daemon=True).start()
    return {"success": True, "message": "Local API process will exit shortly (test hook)"}


@app.post("/shutdown")
async def shutdown(authorization: str | None = Header(default=None)):
    require_auth(authorization)
    audit("shutdown")
    return wait_for_result(submit_command("shutdown_all"), timeout=20)
