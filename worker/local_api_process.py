"""
[AIR-0227B Stage 2] Local API process entry point.

This is the fix for the AIR-0227A skeleton's central problem: Local API ran
as a thread inside the Manager process, and uvicorn.Server.run() executing
in a background thread was root-caused (during AIR-0227A QA) as the reason
the Manager process sometimes wouldn't fully exit even after every owned
thread/child had genuinely stopped - worked around there with a flagged
os._exit(0). Making Local API a true separate subprocess.Popen child (like
Render/Hermes Worker already were) removes the need for that workaround
entirely: this process's own lifecycle is independent of the Manager's, it
gets its own signal handlers, and the Manager just polls/kills it the same
uniform way it already handles the other two child processes.
"""
import json
import signal
import sys
import time

import uvicorn

from logging_setup import get_logger
from shutdown_flag import clear_shutdown_flag, is_shutdown_requested
from worker_config import LOCAL_API_HOST, LOCAL_API_PORT, STATE_DIR

STATE_FILE = STATE_DIR / "local_api.json"
logger = get_logger("local_api")

_server: uvicorn.Server | None = None


def write_state(status: str):
    STATE_FILE.write_text(
        json.dumps({"pid": None, "status": status, "current_job": None, "progress": None, "heartbeat_at": time.time()}, ensure_ascii=False),
        encoding="utf-8",
    )


def _handle_signal(signum, frame):
    # [Windows caveat - see shutdown_flag.py] real-world trigger only for a
    # Ctrl+C in the same console; Popen.terminate() from the Manager does
    # NOT deliver this on Windows. The flag-poll loop below is the real path.
    logger.info(f"Received signal {signum}, requesting graceful uvicorn shutdown")
    if _server is not None:
        _server.should_exit = True


def _heartbeat_loop():
    while _server is not None and not _server.should_exit:
        write_state("running")
        if is_shutdown_requested("local_api"):
            logger.info("Shutdown flag detected, requesting graceful uvicorn shutdown")
            _server.should_exit = True
            break
        time.sleep(1)


def main():
    global _server
    signal.signal(signal.SIGINT, _handle_signal)
    try:
        signal.signal(signal.SIGTERM, _handle_signal)
    except (AttributeError, ValueError):
        pass

    import local_api_app  # noqa: E402  (import after logging_setup is ready)

    clear_shutdown_flag("local_api")  # discard any stale flag from a previous instance of this process
    logger.info(f"Local API starting on {LOCAL_API_HOST}:{LOCAL_API_PORT} (loopback only), pid={__import__('os').getpid()}")
    write_state("starting")

    config = uvicorn.Config(local_api_app.app, host=LOCAL_API_HOST, port=LOCAL_API_PORT, log_level="warning")
    server = uvicorn.Server(config)
    _server = server

    import threading
    threading.Thread(target=_heartbeat_loop, daemon=True).start()

    try:
        server.run()  # blocks the main thread of THIS process only - no longer shares a process with the Manager
    finally:
        write_state("stopped")
        logger.info("Local API process exiting")


if __name__ == "__main__":
    if "--crash-now" in sys.argv:
        logger.info("--crash-now flag set, exiting with non-zero status immediately")
        sys.exit(1)
    main()
