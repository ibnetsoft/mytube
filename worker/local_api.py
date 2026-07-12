"""
[AIR-0227A Stage 12] Local API - 127.0.0.1-only control/status surface.

docs/AIR_WORKER_SECURITY.md §2: must bind to loopback only, never exposed
externally. Runs as a thread inside the Worker Manager process (not a
separate OS process - docs/AIR_WORKER_PROCESS_MODEL.md §5).
"""
import threading
import time
from pathlib import Path

import uvicorn
from fastapi import FastAPI

from config import LOCAL_API_HOST, LOCAL_API_PORT, LOG_FILES
from logging_setup import get_logger

logger = get_logger("local_api")

app = FastAPI(title="AIR Worker Local API (PoC skeleton)")
_manager = None  # set by run_local_api_thread()


@app.get("/health")
async def health():
    return {"status": "ok", "time": time.time()}


@app.get("/status")
async def status():
    return _manager.status_snapshot()


@app.get("/processes")
async def processes():
    return _manager.registry.to_dict()


@app.post("/processes/render/start")
async def render_start():
    ok = _manager.start_process("render_worker")
    return {"success": ok}


@app.post("/processes/render/stop")
async def render_stop():
    ok = _manager.stop_process("render_worker")
    return {"success": ok}


@app.post("/processes/hermes/start")
async def hermes_start():
    ok = _manager.start_process("hermes_worker")
    return {"success": ok}


@app.post("/processes/hermes/stop")
async def hermes_stop():
    ok = _manager.stop_process("hermes_worker")
    return {"success": ok}


@app.get("/jobs")
async def jobs():
    """[AIR-0227A skeleton] Reflects each mock worker's self-reported
    current_job only - there is no real central job queue connected in
    this Task (docs/AIR_WORKER_JOB_PROTOCOL.md §3)."""
    snapshot = _manager.status_snapshot()
    return {
        name: proc.get("current_job")
        for name, proc in snapshot["processes"].items()
        if proc.get("current_job")
    }


@app.get("/logs")
async def logs(process: str = "manager", tail_lines: int = 50):
    path = LOG_FILES.get(process)
    if not path or not Path(path).exists():
        return {"error": f"Unknown or empty log for process '{process}'", "available": list(LOG_FILES.keys())}
    lines = Path(path).read_text(encoding="utf-8", errors="replace").splitlines()
    return {"process": process, "lines": lines[-tail_lines:]}


@app.post("/_test/crash-local-api")
async def test_crash_local_api():
    """[AIR-0227A QA hook only - not a real production endpoint] Simulates
    the Local API dying, to verify the Manager auto-restarts it."""
    logger.warning("QA test hook: simulating Local API crash")
    threading.Thread(target=force_stop_local_api, daemon=True).start()
    return {"success": True, "message": "Local API will stop momentarily (test hook)"}


@app.post("/shutdown")
async def shutdown():
    logger.info("Shutdown requested via Local API")
    threading.Thread(target=_manager.stop_all, daemon=True).start()
    return {"success": True, "message": "Shutting down all processes"}


_current_server: uvicorn.Server | None = None


def force_stop_local_api():
    """[AIR-0227A QA hook] Lets a test simulate the Local API
    'terminating' (e.g. to verify the Manager's auto-recovery,
    docs/AIR_WORKER_PROCESS_MODEL.md §5) without killing the whole Manager
    process, since the API runs as a thread inside it rather than its own
    OS process."""
    if _current_server is not None:
        _current_server.should_exit = True


def run_local_api_thread(manager) -> threading.Thread:
    global _manager, _current_server
    _manager = manager

    def _serve():
        global _current_server
        logger.info(f"Local API starting on {LOCAL_API_HOST}:{LOCAL_API_PORT} (loopback only)")
        try:
            config = uvicorn.Config(app, host=LOCAL_API_HOST, port=LOCAL_API_PORT, log_level="warning")
            server = uvicorn.Server(config)
            _current_server = server
            server.run()
        except Exception as e:
            logger.error(f"Local API server crashed: {e}")
        finally:
            logger.info("Local API thread exiting")

    thread = threading.Thread(target=_serve, daemon=True, name="local-api")
    thread.start()
    return thread
