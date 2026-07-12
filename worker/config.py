"""
[AIR-0227A Stage 12] AIR Worker skeleton - shared configuration.

Standalone module (no imports from services/app/database.py/config.py of
the main AIR Studio app) - the skeleton deliberately does not connect to
the real rendering pipeline or a real Hermes runtime yet
(docs/AIR_WORKER_PROCESS_MODEL.md §7).
"""
import os
from pathlib import Path

# In a real install this would be %LOCALAPPDATA%\AIRWorker\. For this
# skeleton/QA pass we default to a folder inside the worker/ dir itself so
# it never touches the real AIR Studio data directory
# (%LOCALAPPDATA%\AIRStudio\), matching AIR_WORKER_UPDATE_STRATEGY.md §2's
# "완전히 분리된 설치 경로" principle even at the skeleton stage.
BASE_DIR = Path(os.environ.get("AIRWORKER_HOME", Path(__file__).resolve().parent))
STATE_DIR = BASE_DIR / "state"
LOG_DIR = BASE_DIR / "logs"
STATE_DIR.mkdir(parents=True, exist_ok=True)
LOG_DIR.mkdir(parents=True, exist_ok=True)

# docs/AIR_WORKER_PROCESS_MODEL.md §4 - one log file per process, no shared file.
LOG_FILES = {
    "manager": LOG_DIR / "manager.log",
    "render_worker": LOG_DIR / "render_worker.log",
    "hermes_worker": LOG_DIR / "hermes_worker.log",
    "local_api": LOG_DIR / "local_api.log",
    "updater": LOG_DIR / "updater.log",
}

# docs/AIR_WORKER_PROCESS_MODEL.md §3 - bounded auto-restart.
CRASH_WINDOW_SECONDS = 600          # 10 minutes
MAX_CRASHES_IN_WINDOW = 3           # disable the module after this many crashes in the window
RESTART_BACKOFF_SECONDS = 2         # small delay before restarting a crashed process

# docs/AIR_WORKER_PROCESS_MODEL.md §5 - Local API bind address.
# docs/AIR_WORKER_SECURITY.md §2 - MUST be loopback-only, never configurable
# to a real interface address.
LOCAL_API_HOST = "127.0.0.1"
LOCAL_API_PORT = int(os.environ.get("AIRWORKER_LOCAL_API_PORT", "8765"))

HEARTBEAT_STALE_SECONDS = 15        # a process is considered unresponsive if its heartbeat file is older than this
MANAGER_TICK_SECONDS = 1.0          # how often the manager's supervisor loop runs

WORKER_ID = os.environ.get("AIRWORKER_ID", "poc-worker-not-real")
# docs/AIR_WORKER_SECURITY.md §4 - never a real Worker Token, never committed.
WORKER_TOKEN = os.environ.get("AIRWORKER_TOKEN", "poc-worker-token-not-real")
