"""
[AIR-0227B Stage 4/5] Render Job Adapter - wraps the real, already-live
rendering pipeline (services/remote_render_service.py::remote_render_executor_func)
for use by the new Render Worker Process.

Why this function specifically (Stage 1 re-verification, see
worknote/AIR-0227B-stage1-render-pipeline-callflow.md):
  - It takes (task_id, temp_dir, use_gpu=False) and NO Supabase/service_role
    credential of any kind - confirmed by reading it in full.
  - It reads only temp_dir/config.json + asset files already placed under
    temp_dir (audio/, images/, overlays/, ...), and writes progress.txt +
    output.mp4 into that same temp_dir.
  - database.py, imported transitively via services/remote_render_service.py's
    zip-packaging helper (NOT by remote_render_executor_func itself), is
    pure local SQLite - no network credential either.
  This makes it safe to call directly from an untrusted-PC worker process
  that must never hold service_role (docs/AIR_WORKER_SECURITY.md §1).

What this adapter does NOT do: modify remote_render_service.py itself. The
existing render server/pipeline is left completely untouched, per the
task's explicit "기존 렌더링 서버 제거 금지"; this module only prepares its
inputs (temp_dir) and consumes its outputs (progress.txt, output.mp4).
"""
import json
import os
import shutil
import tempfile
import threading
import time
import zipfile
from pathlib import Path
from typing import Callable, Optional

from worker_config import ensure_project_root_on_path, RENDER_ENCODER, RENDER_ACCELERATION, GPU_RENDERING_ACTIVE

ensure_project_root_on_path()


class RenderPipelineError(Exception):
    pass


def prepare_temp_dir(source_path: str) -> Path:
    """Builds a scratch temp_dir the same way remote_drive_worker.py's
    process_job() did (download -> extract -> render -> cleanup), except the
    'download' step is a local file copy instead of a Google Drive fetch
    (docs/AIR_WORKER_RENDER_ADAPTER.md - local E2E fixture uses a local
    source instead of Drive, production would substitute a Drive download
    adapter here without changing anything below this point)."""
    temp_dir = Path(tempfile.mkdtemp(prefix="airworker_render_"))
    src = Path(source_path)
    if not src.exists():
        raise RenderPipelineError(f"Render source not found: {source_path}")

    if src.is_file() and src.suffix.lower() == ".zip":
        with zipfile.ZipFile(src, "r") as zf:
            zf.extractall(temp_dir)
    elif src.is_dir():
        shutil.copytree(src, temp_dir, dirs_exist_ok=True)
    else:
        raise RenderPipelineError(f"Unsupported render source (must be .zip or a directory): {source_path}")

    if not (temp_dir / "config.json").exists():
        raise RenderPipelineError(f"Prepared temp_dir has no config.json: {temp_dir}")
    return temp_dir


def _read_progress_file(temp_dir: Path) -> Optional[dict]:
    p = temp_dir / "progress.txt"
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def run_render(job_id: str, temp_dir: Path, progress_callback: Callable[[int, str], None],
               poll_interval: float = 0.5) -> Path:
    """Runs the real pipeline (blocking, on the calling thread) while a
    background watcher thread tails temp_dir/progress.txt and forwards
    updates to progress_callback. Returns the output.mp4 path on success.

    [AIR-0227B Stage 8 cancellation note] remote_render_executor_func has no
    cancellation hook and this adapter does not add one (the existing
    pipeline is left untouched). Mid-render cancellation is therefore NOT
    achievable by signaling this thread - it requires the caller (Render
    Worker Process) to be killed as a whole, ffmpeg child included via
    process-tree kill. See docs/AIR_WORKER_SHUTDOWN_PROTOCOL.md and
    docs/AIR_WORKER_JOB_RECOVERY.md for the documented policy: cancel while
    QUEUED/CLAIMED is graceful (never started); cancel while
    PREPARING/RENDERING/UPLOADING escalates to a full process-tree kill of
    the Render Worker Process, followed by a fresh process restart."""
    from services.remote_render_service import remote_render_executor_func

    stop_watching = threading.Event()
    last_reported = {"pct": -1}

    def _watch():
        while not stop_watching.is_set():
            state = _read_progress_file(temp_dir)
            if state and state.get("progress") != last_reported["pct"]:
                last_reported["pct"] = state["progress"]
                progress_callback(state["progress"], state.get("message", ""))
            stop_watching.wait(poll_interval)

    watcher = threading.Thread(target=_watch, daemon=True, name=f"progress-watch-{job_id}")
    watcher.start()
    try:
        # use_gpu is intentionally always False - Stage 1/9 finding: no
        # encoding path in this codebase honors this flag, so passing True
        # would be a lie the UI/logs would then have to repeat.
        remote_render_executor_func(job_id, str(temp_dir), use_gpu=False)
    finally:
        stop_watching.set()
        watcher.join(timeout=2)

    final_state = _read_progress_file(temp_dir)
    if final_state and final_state.get("progress") == -1:
        raise RenderPipelineError(final_state.get("message", "Render failed (see progress.txt)"))

    output_path = temp_dir / "output.mp4"
    if not output_path.exists():
        raise RenderPipelineError(f"Render reported success but output.mp4 is missing: {output_path}")
    return output_path


def cleanup_temp_dir(temp_dir: Path):
    shutil.rmtree(temp_dir, ignore_errors=True)


def render_status_display() -> dict:
    """[AIR-0227B Stage 9] Honest CPU/GPU status for Local API /status -
    never claims GPU acceleration is active since nothing in the pipeline
    implements it (Stage 1 finding, worker_config.py)."""
    try:
        from sfx_library import sfx_status
    except Exception:
        sfx = {"catalog_exists": False, "item_count": 0, "existing_file_count": 0}
    else:
        sfx = sfx_status()
    return {
        "encoder": RENDER_ENCODER,
        "acceleration": RENDER_ACCELERATION,
        "gpu_rendering": GPU_RENDERING_ACTIVE,
        "sfx_library": sfx,
    }
