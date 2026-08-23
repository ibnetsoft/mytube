"""
[AIR-0227E] Unified AIRWorker entrypoint - the single script/exe every
process role runs through.

Why this exists: worker/manager.py spawns Render Worker / Hermes Worker /
Local API as separate subprocess.Popen children by pointing at their own
.py file (`[sys.executable, "worker/render_worker.py"]`, etc). That works
when running from source (sys.executable is a real python.exe and the
sibling .py files exist on disk), but breaks the moment AIRWorker is frozen
into a single PyInstaller exe: sys.executable then points at the frozen
exe itself (no python.exe), and render_worker.py/hermes_worker_mock.py/
local_api_process.py no longer exist as standalone files - everything is
bundled inside the one binary. The fix is the standard PyInstaller
multi-role pattern: every process (Manager and all its children) is
actually the same exe, re-invoked with a `--role` flag telling it which
module's main() to run. manager.py picks the right invocation
(`[sys.executable, "--role", name]` when frozen, or
`[sys.executable, "air_worker_entry.py", "--role", name]` from source) -
see worker/manager.py's start_process().

Usage:
  AIRWorker.exe                       -> role=manager (double-click default)
  AIRWorker.exe --role manager
  AIRWorker.exe --role render_worker
  AIRWorker.exe --role remote_drive_worker
  AIRWorker.exe --role hermes_worker
  AIRWorker.exe --role local_api

Each role's module is imported lazily, only after the role is resolved -
resolving `--role local_api` should not require render_worker.py's heavier
transitive dependencies (moviepy, etc.) to already be importable, mirroring
how each of these scripts was only ever imported by the one process that
actually plays that role.
"""
import sys

# [AIR-0227E, found via live build+run QA] manager.py already sets
# PYTHONIOENCODING=utf-8 in every child's env - a fix for the known
# "services/video_service.py prints emoji to stdout, crashes with
# UnicodeEncodeError on a cp949-codepage Windows console" issue
# (worker/manager.py's start_process() comment). That env var reliably
# reconfigures a real python.exe's stdio, but a frozen PyInstaller onefile
# exe's embedded interpreter does not honor it the same way (its bootloader
# sets up stdio before/independently of that env var) - reproduced live:
# the render fixture job crashed with exactly this UnicodeEncodeError only
# in the frozen exe, never in dev-mode `python manager.py`. Reconfiguring
# stdout/stderr explicitly here, at the top of the one entrypoint every
# role runs through, is the fix that actually takes effect regardless of
# how the process was started - `errors="replace"` (not "strict") so an
# unencodable character degrades to a placeholder instead of crashing the
# render pipeline outright, matching the intent of the original PYTHONIOENCODING
# fix (keep going, don't lose a render over a log line).
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass  # non-reconfigurable stream (e.g. redirected to something unusual) - best effort only

# Guarantee .env is loaded into os.environ before any role module imports
try:
    import worker_config  # noqa: F401
except Exception:
    pass

ROLES = ("manager", "render_worker", "remote_drive_worker", "hermes_worker", "local_api")


def _dispatch(role: str, crash_now: bool):
    if role == "manager":
        # 자식 프로세스들(render_worker, hermes_worker, local_api)은 콘솔 유지.
        if sys.platform == "win32":
            try:
                import ctypes
                ctypes.windll.user32.ShowWindow(
                    ctypes.windll.kernel32.GetConsoleWindow(), 0
                )
            except Exception:
                pass
        import manager as mod
    elif role == "render_worker":
        import render_worker as mod
    elif role == "remote_drive_worker":
        import remote_drive_worker_process as mod
    elif role == "hermes_worker":
        import hermes_worker as mod  # [AIR-0227E-P3] real Hermes Worker - hermes_worker_mock.py remains for test-only direct import, never dispatched here
    elif role == "local_api":
        import local_api_process as mod
    else:
        raise ValueError(f"unknown role '{role}' (expected one of {ROLES})")

    if crash_now:
        # Preserves each child script's own `--crash-now` QA hook (manual
        # crash-recovery testing, docs/AIR_WORKER_JOB_RECOVERY.md) even
        # though main() is now called directly instead of going through
        # that module's own `if __name__ == "__main__":` block.
        sys.exit(1)

    mod.main()


def main():
    args = sys.argv[1:]
    role = "manager"
    if "--role" in args:
        idx = args.index("--role")
        try:
            role = args[idx + 1]
        except IndexError:
            print("--role requires a value", file=sys.stderr)
            sys.exit(2)
        if role not in ROLES:
            print(f"unknown --role '{role}', expected one of {ROLES}", file=sys.stderr)
            sys.exit(2)
    crash_now = "--crash-now" in args
    _dispatch(role, crash_now)


if __name__ == "__main__":
    main()
