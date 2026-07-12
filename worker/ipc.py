"""
[AIR-0227B Stage 2] File-based command/result IPC between the Local API
Process and the Worker Manager.

Local API is now its own OS process (Stage 2 requirement), so it can no
longer call manager.status_snapshot()/start_process()/stop_process() as
in-process Python calls the way AIR-0227A's thread-based version did. For
read-only status, Local API reads the same state files/job_store.db the
Manager already writes (no IPC needed there). For control actions
(start/stop a process, shutdown, cancel a job) it needs to ask the Manager
to actually do it, since only the Manager owns the subprocess.Popen handles.

This uses the same file-polling IPC pattern already established between the
Manager and Render/Hermes Worker (heartbeat state files) rather than adding
a second network protocol - the Manager's existing 1s supervisor tick just
gains one more thing to check per loop.
"""
import json
import time
import uuid
from pathlib import Path
from typing import Optional

from worker_config import COMMAND_DIR, RESULT_DIR, COMMAND_RESULT_TIMEOUT_SECONDS


def submit_command(command: str, params: Optional[dict] = None) -> str:
    command_id = str(uuid.uuid4())
    payload = {"command_id": command_id, "command": command, "params": params or {}, "submitted_at": time.time()}
    tmp = COMMAND_DIR / f"{command_id}.json.tmp"
    final = COMMAND_DIR / f"{command_id}.json"
    tmp.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    tmp.rename(final)  # atomic on the same filesystem - avoids the Manager reading a half-written file
    return command_id


def wait_for_result(command_id: str, timeout: float = COMMAND_RESULT_TIMEOUT_SECONDS) -> dict:
    result_path = RESULT_DIR / f"{command_id}.json"
    deadline = time.time() + timeout
    while time.time() < deadline:
        if result_path.exists():
            try:
                data = json.loads(result_path.read_text(encoding="utf-8"))
                result_path.unlink(missing_ok=True)
                return data
            except (json.JSONDecodeError, OSError):
                pass
        time.sleep(0.1)
    return {"success": False, "error": f"Manager did not respond to command within {timeout}s (is it running?)"}


def pending_commands() -> list[Path]:
    return sorted(COMMAND_DIR.glob("*.json"))


def read_command(path: Path) -> Optional[dict]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def write_result(command_id: str, result: dict):
    tmp = RESULT_DIR / f"{command_id}.json.tmp"
    final = RESULT_DIR / f"{command_id}.json"
    tmp.write_text(json.dumps(result, ensure_ascii=False), encoding="utf-8")
    tmp.rename(final)


def consume_command(path: Path):
    path.unlink(missing_ok=True)
