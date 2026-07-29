"""
[AIR-0227E-P2] Manager-only single-instance enforcement via a Windows Named
Mutex.

Deliberately NOT wired into worker/air_worker_entry.py's shared `--role`
dispatch - only worker/manager.py's main() calls acquire_or_exit(). Render
Worker / Hermes Worker / Local API are always spawned BY a Manager
(worker/manager.py::_child_command()) and have no way to distinguish "my
own Manager is still alive" from "some other Manager owns this machine now" -
making a child refuse to start on a mutex conflict would just break a
legitimate restart of that one role. Single-instance enforcement only makes
sense at the Manager level, which is the one process type that is ever
launched independently (double-click, Task Scheduler, etc).

The mutex is machine-wide (`Global\\` prefix, session-0-visible) rather than
scoped per AIRWORKER_HOME - the intent is "one AIR Worker Manager per
rendering PC" (docs/AIR_WORKER_ARCHITECTURE.md's whole premise), not
"one per data directory". A held mutex handle is automatically released by
Windows when its owning process exits for any reason (graceful shutdown or
crash), so no manual cleanup/unlock step is needed here.
"""
import sys

MUTEX_NAME = "Global\\AIRWorker_Manager_SingleInstance"

_mutex_handle = None  # module-level reference - must outlive the process, never closed except on the refused-second-instance path


def acquire_or_exit(logger) -> None:
    """Call once, at the very top of the Manager's main(). Exits the process
    (sys.exit(1)) if another Manager already holds the mutex - never returns
    in that case."""
    global _mutex_handle
    if sys.platform != "win32":
        logger.warning("single_instance: non-Windows platform, skipping Named Mutex check (dev-only no-op)")
        return

    import win32api
    import win32event
    import winerror

    handle = win32event.CreateMutex(None, False, MUTEX_NAME)
    already_running = (win32api.GetLastError() == winerror.ERROR_ALREADY_EXISTS)
    if already_running:
        logger.error(
            f"Another AIR Worker Manager already holds mutex '{MUTEX_NAME}' on this "
            f"machine - refusing to start a second instance (docs/AIR_WORKER_RUNTIME.md "
            f"§6.7/P2 §single-instance)."
        )
        win32api.CloseHandle(handle)
        logger.error(f"This instance's own exit code will be 1. {_describe_existing_instance()}")
        sys.exit(1)

    _mutex_handle = handle
    logger.info(f"Acquired single-instance mutex '{MUTEX_NAME}'")


def _describe_existing_instance() -> str:
    """[P2 §4 second-launch UX] Best-effort, unauthenticated check of the
    presumably-already-running instance's Local API /health - never touches
    or logs the auth token (that endpoint is deliberately the one
    unauthenticated route, worker/local_api_app.py). Any failure here is
    swallowed and reported as "unknown" - this is purely informational for
    the refusal message, never a reason to change the refuse-to-start
    decision itself."""
    try:
        import requests
        from worker_config import LOCAL_API_HOST, LOCAL_API_PORT
        r = requests.get(f"http://{LOCAL_API_HOST}:{LOCAL_API_PORT}/health", timeout=2)
        if r.status_code == 200:
            return f"Existing instance's Local API /health responded OK ({r.json().get('status', '?')})."
        return f"Existing instance's Local API /health responded with unexpected status {r.status_code}."
    except Exception as e:
        return f"Could not reach existing instance's Local API /health (non-fatal, informational only): {type(e).__name__}"
