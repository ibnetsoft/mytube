"""
[AIR-0227B Stage 1] AIR Worker shared configuration.

Named worker_config.py (not config.py) deliberately: the Render Worker
Process now imports services/remote_render_service.py, which itself does
`from config import config` expecting the *main AIR Studio app's* root
config.py. Since worker/ is the child script's own directory, it is always
sys.path[0] for these subprocess.Popen'd scripts - a module named
config.py living in here would permanently shadow the real one and break
every real-pipeline import. Renaming this module is the fix.
"""
import os
import json
import sys
from pathlib import Path


def _load_worker_env():
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    candidates = []
    if getattr(sys, "frozen", False):
        exe_dir = Path(sys.executable).resolve().parent
        candidates.append(exe_dir / ".env")
        candidates.append(exe_dir / "_internal" / ".env")
        if getattr(sys, "_MEIPASS", None):
            candidates.append(Path(sys._MEIPASS) / ".env")
    candidates.append(Path.cwd() / ".env")
    candidates.append(Path(__file__).resolve().parent / ".env")
    candidates.append(Path(__file__).resolve().parent.parent / ".env")
    seen = set()
    for p in candidates:
        try:
            rp = p.resolve()
            if rp not in seen and rp.is_file():
                seen.add(rp)
                load_dotenv(rp, override=False)
        except Exception:
            pass


_load_worker_env()

# [AIR-0227E-P2-VALIDATION] The installed binaries live under Program Files
# (Inno Setup's AIRWorker.iss, admin-required) - a standard user cannot
# write there. All mutable state must live somewhere the user account
# running AIRWorker.exe can always write to, regardless of install location
# or privilege level. Final confirmed path: %LOCALAPPDATA%\AIRStudio\AIRWorker\
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

OUTPUT_DIR = BASE_DIR / "output"
TEMP_DIR = BASE_DIR / "temp"
CONFIG_DIR = BASE_DIR / "config"
ASSET_DIR = BASE_DIR / "assets"
SFX_LIBRARY_DIR = ASSET_DIR / "sfx"
SFX_CATALOG_PATH = SFX_LIBRARY_DIR / "catalog.json"
CRASH_DIR = BASE_DIR / "crash"
UPDATE_DIR = BASE_DIR / "update"
QUARANTINE_DIR = BASE_DIR / "quarantine"
for _d in (STATE_DIR, LOG_DIR, JOB_LOG_DIR, IPC_DIR, COMMAND_DIR, RESULT_DIR,
           CANCEL_FLAG_DIR, SHUTDOWN_FLAG_DIR, OUTPUT_DIR, TEMP_DIR, CONFIG_DIR,
           ASSET_DIR, SFX_LIBRARY_DIR, CRASH_DIR, UPDATE_DIR, QUARANTINE_DIR):
    _d.mkdir(parents=True, exist_ok=True)

JOB_DB_PATH = STATE_DIR / "jobs.db"
WORKER_SETTINGS_FILE = CONFIG_DIR / "worker_settings.json"


def _load_worker_settings_file() -> None:
    if not WORKER_SETTINGS_FILE.is_file():
        return
    try:
        data = json.loads(WORKER_SETTINGS_FILE.read_text(encoding="utf-8"))
    except Exception:
        return
    values = data.get("env", data) if isinstance(data, dict) else {}
    if not isinstance(values, dict):
        return
    for key, value in values.items():
        if not isinstance(key, str) or value is None:
            continue
        os.environ[key] = str(value)


_load_worker_settings_file()

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
LOCAL_API_HOST = "127.0.0.1"
LOCAL_API_PORT = int(os.environ.get("AIRWORKER_LOCAL_API_PORT", "8765"))

HEARTBEAT_STALE_SECONDS = 15        # a process is considered unresponsive if its heartbeat file is older than this
MANAGER_TICK_SECONDS = 1.0          # how often the manager's supervisor loop runs

# [AIR-0227B Stage 3] graceful shutdown protocol timings
SHUTDOWN_GRACE_SECONDS = 8.0
SHUTDOWN_JOB_ABORT_GRACE_SECONDS = 5.0
COMMAND_RESULT_TIMEOUT_SECONDS = 10.0

WORKER_ID = os.environ.get("AIRWORKER_ID", "poc-worker-not-real")
WORKER_TOKEN = os.environ.get("AIRWORKER_TOKEN", "poc-worker-token-not-real")

WORKER_PROFILES = ("full", "content_only", "render_only")
PROFILE_CHILD_SCRIPTS = {
    "full": ("render_worker", "remote_drive_worker", "hermes_worker", "local_api"),
    "content_only": ("hermes_worker", "local_api"),
    "render_only": ("render_worker", "remote_drive_worker", "local_api"),
}


def normalize_worker_profile(value: str | None) -> str:
    normalized = str(value or "").strip().lower().replace("-", "_")
    aliases = {
        "": "full",
        "all": "full",
        "default": "full",
        "both": "full",
        "content": "content_only",
        "script": "content_only",
        "script_only": "content_only",
        "hermes": "content_only",
        "hermes_only": "content_only",
        "generation": "content_only",
        "generation_only": "content_only",
        "render": "render_only",
        "renderer": "render_only",
        "rendering": "render_only",
    }
    return aliases.get(normalized, normalized if normalized in WORKER_PROFILES else "full")


WORKER_PROFILE = normalize_worker_profile(
    os.environ.get("AIRWORKER_PROFILE") or os.environ.get("AIR_WORKER_PROFILE")
)
ALLOWED_CHILD_SCRIPTS = PROFILE_CHILD_SCRIPTS[WORKER_PROFILE]

WORKER_INSTANCE_ID = os.environ.get("AIRWORKER_INSTANCE_ID") or __import__("uuid").uuid4().hex

PROJECT_ROOT = Path(os.environ.get("AIRWORKER_PROJECT_ROOT", Path(__file__).resolve().parent.parent))


def ensure_project_root_on_path():
    root = str(PROJECT_ROOT)
    if root not in sys.path:
        sys.path.insert(0, root)


RENDER_ENCODER = "libx264"
RENDER_ACCELERATION = "CPU"
GPU_RENDERING_ACTIVE = False

# ── 시스템 트레이 설정 ──
TRAY_POLL_INTERVAL_SECONDS = 3.0
TRAY_ICON_NAME = "AIR Worker"

# ── 웹 대시보드 설정 ──
DASHBOARD_HOST = "127.0.0.1"
DASHBOARD_PORT = 3002


def _looks_like_masked_secret(value: str) -> bool:
    normalized = str(value or "").strip()
    if not normalized:
        return False
    return any(ord(ch) == 8226 for ch in normalized) or normalized.startswith("****")


def save_worker_settings(new_settings: dict) -> dict:
    """Save worker settings (profile, worker_id, central url, token, etc.) to .env and os.environ."""
    global WORKER_PROFILE, ALLOWED_CHILD_SCRIPTS, WORKER_ID, WORKER_TOKEN

    key_map = {
        "supabase_url": "NEXT_PUBLIC_SUPABASE_URL",
        "supabase_service_role_key": "SUPABASE_SERVICE_ROLE_KEY",
        "worker_profile": "AIRWORKER_PROFILE",
        "worker_id": "AIRWORKER_ID",
        "central_server_url": "AIRWORKER_CENTRAL_SERVER_URL",
        "worker_token": "AIRWORKER_TOKEN",
        "remote_worker_id": "REMOTE_RENDER_WORKER_ID",
        "remote_google_token_path": "REMOTE_RENDER_GOOGLE_TOKEN_PATH",
        "remote_drive_folder_id": "REMOTE_RENDER_DRIVE_FOLDER_ID",
        "use_gpu_render": "USE_GPU_RENDER",
        "notion_api_key": "NOTION_API_KEY",
        "notion_learning_database_id": "NOTION_LEARNING_DATABASE_ID",
    }

    updates = {}
    for param_key, env_key in key_map.items():
        if param_key in new_settings:
            val = str(new_settings[param_key] or "").strip()
            if param_key in ("worker_token", "notion_api_key") and _looks_like_masked_secret(val):
                continue  # skip masked token
            updates[env_key] = val
            os.environ[env_key] = val

    # Apply in-memory variables
    if "AIRWORKER_PROFILE" in updates:
        WORKER_PROFILE = normalize_worker_profile(updates["AIRWORKER_PROFILE"])
        ALLOWED_CHILD_SCRIPTS = PROFILE_CHILD_SCRIPTS[WORKER_PROFILE]
    if "AIRWORKER_ID" in updates:
        WORKER_ID = updates["AIRWORKER_ID"]
    if "AIRWORKER_TOKEN" in updates:
        WORKER_TOKEN = updates["AIRWORKER_TOKEN"]

    written_paths = []
    try:
        existing = {}
        if WORKER_SETTINGS_FILE.is_file():
            loaded = json.loads(WORKER_SETTINGS_FILE.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                existing = loaded.get("env", loaded) if isinstance(loaded.get("env", loaded), dict) else {}
        persisted = {**existing, **updates}
        WORKER_SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
        WORKER_SETTINGS_FILE.write_text(
            json.dumps({"env": persisted}, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        written_paths.append(str(WORKER_SETTINGS_FILE))
    except Exception:
        pass

    return {
        "success": True,
        "worker_profile": WORKER_PROFILE,
        "worker_id": WORKER_ID,
        "updated_keys": list(updates.keys()),
        "written_files": written_paths,
    }
