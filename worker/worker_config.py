"""
[AIR-0227B Stage 1] AIR Worker shared configuration.

Named worker_config.py (not config.py) deliberately: the Render Worker
Process now imports services/remote_render_service.py, which itself does
`from config import config` expecting the *main AIR Studio app's* root
config.py. Since worker/ is the child script's own directory, it is always
sys.path[0] for these subprocess.Popen'd scripts - a module named
config.py living in here would permanently shadow the real one and break
every real-pipeline import. Renaming this module is the fix (AIR-0227A's
worker/config.py caused no problem only because nothing under worker/ ever
imported the real pipeline yet - AIR-0227B is the first Task that does).
"""
import os
import sys
from pathlib import Path

# [AIR-0227E-P2-VALIDATION] The installed binaries live under Program Files
# (Inno Setup's AIRWorker.iss, admin-required) - a standard user cannot
# write there. All mutable state must live somewhere the user account
# running AIRWorker.exe can always write to, regardless of install location
# or privilege level. Final confirmed path (per this Task's explicit
# decision, superseding the P2 hardening branch's standalone
# %LOCALAPPDATA%\AIRWorker\): %LOCALAPPDATA%\AIRStudio\AIRWorker\ - nested
# under the same top-level vendor folder AIR Studio Desktop already uses
# (%LOCALAPPDATA%\AIRStudio\), as a SIBLING data directory. This is a data-
# location choice only, not a channel merge: install path, registry Run key,
# version source (worker_version.py), and update mechanism all remain fully
# independent of AIR Studio Desktop's own channel.
#
# No production users exist yet for AIR Worker (still Conditional Go, never
# deployed) - there is nothing to migrate, so this is a direct default-path
# change, not a migration. A pre-existing dev-only %LOCALAPPDATA%\AIRWorker\
# directory from earlier PoC/QA sessions is simply orphaned (ignored, not
# read, not deleted) - it holds no real data.
#
# AIRWORKER_HOME remains the override for dev/QA/tests that want an
# isolated, disposable location instead of touching the real user profile -
# confirmed still takes priority whenever set (regression-tested).
_DEFAULT_LOCALAPPDATA_HOME = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local")) / "AIRStudio" / "AIRWorker"
BASE_DIR = Path(os.environ.get("AIRWORKER_HOME", _DEFAULT_LOCALAPPDATA_HOME))
STATE_DIR = BASE_DIR / "state"
LOG_DIR = BASE_DIR / "logs"
JOB_LOG_DIR = LOG_DIR / "jobs"
IPC_DIR = BASE_DIR / "ipc"
COMMAND_DIR = IPC_DIR / "commands"
RESULT_DIR = IPC_DIR / "results"
CANCEL_FLAG_DIR = STATE_DIR / "cancel_flags"
SHUTDOWN_FLAG_DIR = STATE_DIR / "shutdown_flags"
MANAGER_STATUS_FILE = STATE_DIR / "manager_status.json"
# [P2-VALIDATION §1] Canonical subpath set. output/ is in active use
# (render_worker.py's DELIVERED_DIR, renamed from state/delivered/). temp/,
# config/, crash/, update/, quarantine/ are created for structural
# completeness but have no consumer yet - reserved, not wired into any
# code path this Task (documented honestly in the worknote, not claimed as
# implemented features).
OUTPUT_DIR = BASE_DIR / "output"
TEMP_DIR = BASE_DIR / "temp"            # reserved - render scratch still uses tempfile.mkdtemp() under system %TEMP%, not migrated here
CONFIG_DIR = BASE_DIR / "config"        # reserved - no user-editable config file lives here yet
CRASH_DIR = BASE_DIR / "crash"          # reserved - no crash-dump writer exists yet
UPDATE_DIR = BASE_DIR / "update"        # reserved worker runtime directory
QUARANTINE_DIR = BASE_DIR / "quarantine"  # reserved - partial/abandoned render outputs are not yet moved here (see docs/AIR_WORKER_JOB_RECOVERY.md for current abandon policy)
for _d in (STATE_DIR, LOG_DIR, JOB_LOG_DIR, IPC_DIR, COMMAND_DIR, RESULT_DIR,
           CANCEL_FLAG_DIR, SHUTDOWN_FLAG_DIR, OUTPUT_DIR, TEMP_DIR, CONFIG_DIR,
           CRASH_DIR, UPDATE_DIR, QUARANTINE_DIR):
    _d.mkdir(parents=True, exist_ok=True)

JOB_DB_PATH = STATE_DIR / "jobs.db"

# docs/AIR_WORKER_PROCESS_MODEL.md §4 - one log file per process, no shared file.
LOG_FILES = {
    "manager": LOG_DIR / "manager.log",
    "render_worker": LOG_DIR / "render_worker.log",
    "remote_drive_worker": LOG_DIR / "remote_drive_worker.log",
    "hermes_worker": LOG_DIR / "hermes_worker.log",
    "local_api": LOG_DIR / "local_api.log",
    "updater": LOG_DIR / "updater.log",
    # 시스템 트레이 관련 로거 — 모두 Manager 프로세스 내부에서 실행
    "tray_app": LOG_DIR / "tray_app.log",
    "tray_notification": LOG_DIR / "tray_notification.log",
    "tray_status_collector": LOG_DIR / "tray_status_collector.log",
    # 웹 대시보드 — Manager 프로세스 내부 daemon 스레드
    "dashboard": LOG_DIR / "dashboard.log",
}

# docs/AIR_WORKER_PROCESS_MODEL.md §3 - bounded auto-restart.
CRASH_WINDOW_SECONDS = 600          # 10 minutes
MAX_CRASHES_IN_WINDOW = 3           # disable the module after this many crashes in the window
RESTART_BACKOFF_SECONDS = 2         # small delay before restarting a crashed process

# docs/AIR_WORKER_SECURITY.md §2 - Local API bind address.
# MUST be loopback-only, never configurable to a real interface address.
LOCAL_API_HOST = "127.0.0.1"
LOCAL_API_PORT = int(os.environ.get("AIRWORKER_LOCAL_API_PORT", "8765"))

HEARTBEAT_STALE_SECONDS = 15        # a process is considered unresponsive if its heartbeat file is older than this
MANAGER_TICK_SECONDS = 1.0          # how often the manager's supervisor loop runs

# [AIR-0227B Stage 3] graceful shutdown protocol timings (docs/AIR_WORKER_SHUTDOWN_PROTOCOL.md).
SHUTDOWN_GRACE_SECONDS = 8.0        # time given to a child process to exit cleanly after SIGTERM/terminate()
SHUTDOWN_JOB_ABORT_GRACE_SECONDS = 5.0  # extra time given to Render Worker to reach a safe checkpoint if a job is active
COMMAND_RESULT_TIMEOUT_SECONDS = 10.0   # how long Local API waits for Manager to answer a command via ipc.py

WORKER_ID = os.environ.get("AIRWORKER_ID", "poc-worker-not-real")
# docs/AIR_WORKER_SECURITY.md §4 - never a real Worker Token, never committed.
WORKER_TOKEN = os.environ.get("AIRWORKER_TOKEN", "poc-worker-token-not-real")

# [AIR-0227C Stage 6] Identity of THIS Manager run, not the OS PID.
# docs/AIR_WORKER_LEASE_PROTOCOL.md: PID is unusable as a stable identity
# (AIR-0227B found the venv launcher relaunches into a child with a
# different pid than the one subprocess.Popen returns - see
# AIR_WORKER_JOB_RECOVERY.md's "pid 불일치" bug writeup). manager.py
# generates ONE uuid4 per Manager process start and exports it via this env
# var to every child it spawns, so Render Worker's lease claims are
# attributable to a stable "this Manager session" identity instead. A
# script run standalone (no Manager) falls back to generating its own -
# only meaningful for ad hoc local testing, never for a real lease claim.
WORKER_INSTANCE_ID = os.environ.get("AIRWORKER_INSTANCE_ID") or __import__("uuid").uuid4().hex

# [AIR-0227B Stage 4] Root of the main AIR Studio app (this repo), needed so
# the Render Worker Process can import services/remote_render_service.py and
# services/video_service.py - the one real, already-battle-tested rendering
# code path (docs/AIR_WORKER_RENDER_ADAPTER.md). This does NOT pull in any
# Supabase/service_role dependency - services/remote_render_service.py's
# remote_render_executor_func() takes no credentials at all, and
# database.py (imported transitively) is pure local SQLite (verified
# Stage 1). Only the Render Worker Process needs this; Manager/Hermes/Local
# API never import project-root modules.
PROJECT_ROOT = Path(os.environ.get("AIRWORKER_PROJECT_ROOT", Path(__file__).resolve().parent.parent))


def ensure_project_root_on_path():
    root = str(PROJECT_ROOT)
    if root not in sys.path:
        sys.path.insert(0, root)


# [AIR-0227B Stage 9] Honest GPU/CPU status display - docs/AIR_WORKER_ARCHITECTURE.md
# Stage 1 finding: no encoding path in this codebase actually uses GPU
# acceleration (zero hits for nvenc|qsv|amf|cuda|hwaccel anywhere in the
# rendering code). remote_render_executor_func's use_gpu parameter is
# accepted but never read. Do not imply GPU accel is happening.
RENDER_ENCODER = "libx264"
RENDER_ACCELERATION = "CPU"
GPU_RENDERING_ACTIVE = False

# ── 시스템 트레이 설정 ──
TRAY_POLL_INTERVAL_SECONDS = 3.0   # 상태 폴링 주기
TRAY_ICON_NAME = "AIR Worker"

# ── 웹 대시보드 설정 ──
DASHBOARD_HOST = "127.0.0.1"
DASHBOARD_PORT = 3002
