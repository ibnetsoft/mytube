"""
AIR Worker Dashboard — daemon-thread launcher for the 3002-port uvicorn.

Unlike the Local API (which is a true child process via Popen), the dashboard
runs inside the Manager process as a daemon thread so it shares the same
job_store SQLite connection and can read manager_status.json without IPC.

Usage (called from manager.py main()):
    from dashboard_server import start_dashboard
    dashboard = start_dashboard()
    # … later, at shutdown …
    dashboard.should_exit = True
"""
import threading

import uvicorn

from logging_setup import get_logger
from worker_config import DASHBOARD_HOST, DASHBOARD_PORT

logger = get_logger("dashboard")


def start_dashboard() -> uvicorn.Server:
    """Start the dashboard FastAPI app on a daemon thread.

    Returns the uvicorn.Server instance so the caller can set
    ``server.should_exit = True`` to shut it down cleanly.
    """
    import dashboard_app  # noqa: E402 — imported here so module-level
    # side-effects (logging_setup.init()) are already done by the time
    # manager.py calls start_dashboard().

    config = uvicorn.Config(
        dashboard_app.app,
        host=DASHBOARD_HOST,
        port=DASHBOARD_PORT,
        log_level="warning",
    )
    server = uvicorn.Server(config)

    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()

    logger.info(f"Dashboard listening on http://{DASHBOARD_HOST}:{DASHBOARD_PORT}")
    return server
