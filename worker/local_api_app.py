"""
[AIR-0227B Stage 2] Local API - now a genuinely separate OS process (was an
in-process thread of the Manager in AIR-0227A). docs/AIR_WORKER_SECURITY.md
§2: loopback-only, never exposed externally.

Read-only endpoints (/health, /status, /processes, /jobs, /logs) read
directly from files the Manager already writes (manager_status.json,
per-process heartbeat state files, job_store.db) - no IPC needed, same
polling-file pattern already used between the Manager and the Render/Hermes
Worker processes.

Control endpoints (start/stop a process, shutdown, cancel a job) cannot be
in-process calls anymore since this is a different OS process than the
Manager that actually owns the subprocess.Popen handles - they go through
worker/ipc.py's file-based command/result channel instead.
"""
import json
import time
from pathlib import Path

import job_store
from fastapi import FastAPI
from ipc import submit_command, wait_for_result
from render_pipeline_adapter import render_status_display
from worker_config import LOG_FILES, STATE_DIR, WORKER_ID

logger = None  # set by local_api_process.py after logging_setup is initialized in this process

app = FastAPI(title="AIR Worker Local API")

MANAGER_STATUS_FILE = STATE_DIR / "manager_status.json"


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
async def status():
    snap = _read_manager_status()
    snap["render_status"] = render_status_display()
    return snap


@app.get("/processes")
async def processes():
    return _read_manager_status().get("processes", {})


@app.post("/processes/render/start")
async def render_start():
    return wait_for_result(submit_command("start_process", {"name": "render_worker"}))


@app.post("/processes/render/stop")
async def render_stop():
    return wait_for_result(submit_command("stop_process", {"name": "render_worker"}))


@app.post("/processes/hermes/start")
async def hermes_start():
    return wait_for_result(submit_command("start_process", {"name": "hermes_worker"}))


@app.post("/processes/hermes/stop")
async def hermes_stop():
    return wait_for_result(submit_command("stop_process", {"name": "hermes_worker"}))


@app.get("/jobs")
async def jobs(status: str | None = None, limit: int = 50):
    return {"jobs": job_store.list_jobs(status=status, limit=limit)}


@app.get("/jobs/{job_id}")
async def job_detail(job_id: str):
    job = job_store.get_job(job_id)
    if not job:
        return {"error": "not found"}
    job["transitions"] = job_store.transition_history(job_id)
    return job


@app.post("/jobs/submit")
async def submit_job(body: dict):
    job_id = job_store.submit_job(
        job_type=body.get("job_type", "render_video"),
        payload=body.get("payload", {}),
        priority=body.get("priority", 100),
        source=body.get("source", "local_api"),
        max_retries=body.get("max_retries", 3),
    )
    return {"job_id": job_id}


@app.post("/jobs/{job_id}/cancel")
async def cancel_job(job_id: str):
    """docs/AIR_WORKER_JOB_RECOVERY.md cancellation policy: QUEUED/CLAIMED/
    PREPARING can be cancelled without killing any process; RENDERING/
    UPLOADING require the Manager to process-tree-kill the Render Worker -
    submitted as a command either way since only the Manager can safely
    decide + execute which path applies (it knows the live process pid)."""
    return wait_for_result(submit_command("cancel_job", {"job_id": job_id}), timeout=15)


@app.get("/logs")
async def logs(process: str = "manager", tail_lines: int = 50):
    path = LOG_FILES.get(process)
    if not path or not Path(path).exists():
        return {"error": f"Unknown or empty log for process '{process}'", "available": list(LOG_FILES.keys())}
    lines = Path(path).read_text(encoding="utf-8", errors="replace").splitlines()
    return {"process": process, "lines": lines[-tail_lines:]}


@app.post("/_test/crash-local-api")
async def test_crash_local_api():
    """[QA hook only] Simulates this whole process dying, to verify the
    Manager auto-restarts it (now a real process-level restart, not a
    thread restart as in AIR-0227A)."""
    import os
    import threading

    def _die():
        time.sleep(0.2)
        os._exit(1)

    threading.Thread(target=_die, daemon=True).start()
    return {"success": True, "message": "Local API process will exit shortly (test hook)"}


@app.post("/shutdown")
async def shutdown():
    return wait_for_result(submit_command("shutdown_all"), timeout=20)
