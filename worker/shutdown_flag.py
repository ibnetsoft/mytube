"""
[AIR-0227B Stage 3 fix] File-based graceful shutdown signaling.

Why not OS signals: on Windows, subprocess.Popen.terminate() calls
Win32 TerminateProcess() - an unconditional hard kill. It does NOT deliver
SIGTERM to the child in any form Python's signal.signal(SIGTERM, ...)
handler will ever see (that only works for POSIX-style signal delivery,
which Windows subprocesses spawned this way don't get). The AIR-0227A
skeleton's SIGINT/SIGTERM handlers in the mock workers only ever actually
fired for a real Ctrl+C in the same console - never for a Manager-issued
Popen.terminate(). Discovered while re-verifying the shutdown design for
this Task, before it could become a QA-only-discovered bug like AIR-0227A's
os._exit issue was.

Fix: reuse the same file-polling pattern already used everywhere else in
this architecture (heartbeat state files, pause flag, cancel flags, command
channel) for shutdown requests too - the Manager writes a per-process flag
file, each child's main loop polls it once per iteration, and only if the
child hasn't self-exited within the Manager's timeout does stop_process()
escalate to an actual terminate()/kill() (which on Windows IS an
unconditional TerminateProcess - fine as the escalation path, just not
acceptable as the *only* path).
"""
from worker_config import SHUTDOWN_FLAG_DIR


def request_shutdown(name: str):
    (SHUTDOWN_FLAG_DIR / f"{name}.flag").write_text("shutdown", encoding="utf-8")


def is_shutdown_requested(name: str) -> bool:
    return (SHUTDOWN_FLAG_DIR / f"{name}.flag").exists()


def clear_shutdown_flag(name: str):
    (SHUTDOWN_FLAG_DIR / f"{name}.flag").unlink(missing_ok=True)
