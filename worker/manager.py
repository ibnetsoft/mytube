"""
[AIR-0227A Stage 12] Worker Manager - the AIRWorker.exe entry point.

docs/AIR_WORKER_ARCHITECTURE.md §1, docs/AIR_WORKER_PROCESS_MODEL.md.

Responsibilities implemented in this skeleton:
  - spawn/stop/restart the Render Worker and Hermes Worker as separate OS
    processes (subprocess.Popen, never merged into this process - the
    task's explicit "단일 Python 프로세스로 합치지 않는다" requirement)
  - track PID + status per process (process_registry.ProcessRegistry)
  - poll each child's heartbeat state file, detect crashes/staleness
  - bounded auto-restart, disable-on-repeated-crash
  - simplified resource policy: render job active -> pause Hermes
    (docs/AIR_WORKER_RESOURCE_POLICY.md §2/§3)
  - run the Local API (docs/AIR_WORKER_SECURITY.md §2) as an in-process thread

NOT implemented here (explicitly out of scope for this Task, see the
prohibitions list in the task and docs/AIR_WORKER_ARCHITECTURE.md §0):
  - real rendering pipeline connection
  - real Hermes runtime connection
  - real central-server job feed / Worker Token verification against a
    live server
  - real auto-updater download/swap logic
"""
import json
import subprocess
import sys
import threading
import time
from pathlib import Path

from config import (
    HEARTBEAT_STALE_SECONDS,
    LOCAL_API_HOST,
    LOCAL_API_PORT,
    MANAGER_TICK_SECONDS,
    RESTART_BACKOFF_SECONDS,
    STATE_DIR,
)
from logging_setup import get_logger
from process_registry import ProcessRegistry

logger = get_logger("manager")

HERE = Path(__file__).resolve().parent
PYTHON = sys.executable

CHILD_SCRIPTS = {
    "render_worker": HERE / "render_worker_mock.py",
    "hermes_worker": HERE / "hermes_worker_mock.py",
}
STATE_FILES = {
    "render_worker": STATE_DIR / "render_worker.json",
    "hermes_worker": STATE_DIR / "hermes_worker.json",
}
PAUSE_FLAG_FILE = STATE_DIR / "hermes_worker.pause"


class WorkerManager:
    def __init__(self):
        self.registry = ProcessRegistry()
        self.popens: dict[str, subprocess.Popen] = {}
        self._lock = threading.Lock()
        self._stopping = False
        self._api_thread: threading.Thread | None = None
        for name in CHILD_SCRIPTS:
            self.registry.register(name)
        self.registry.register("local_api")
        self.registry.register("updater")

    # ---- process lifecycle -------------------------------------------------

    def start_process(self, name: str) -> bool:
        with self._lock:
            rec = self.registry.get(name)
            if rec.status == "disabled":
                logger.warning(f"Refusing to start '{name}' - disabled ({rec.disabled_reason})")
                return False
            if name in self.popens and self.popens[name].poll() is None:
                logger.info(f"'{name}' already running (pid={self.popens[name].pid})")
                return True

            script = CHILD_SCRIPTS[name]
            logger.info(f"Starting '{name}' ({script.name})")
            popen = subprocess.Popen([PYTHON, str(script)], cwd=str(HERE))
            self.popens[name] = popen
            rec.pid = popen.pid
            rec.status = "starting"
            rec.started_at = time.time()
            rec.restart_count_total += 1
            return True

    def stop_process(self, name: str, timeout: float = 5.0) -> bool:
        with self._lock:
            popen = self.popens.get(name)
            rec = self.registry.get(name)
            if not popen or popen.poll() is not None:
                rec.status = "stopped"
                rec.pid = None
                return True
            logger.info(f"Stopping '{name}' (pid={popen.pid})")
            popen.terminate()
            try:
                popen.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                logger.warning(f"'{name}' did not exit within {timeout}s, killing")
                popen.kill()
                popen.wait(timeout=5)
            rec.status = "stopped"
            rec.pid = None
            return True

    def restart_process(self, name: str):
        self.stop_process(name)
        time.sleep(RESTART_BACKOFF_SECONDS)
        self.start_process(name)

    def start_all(self):
        logger.info("Worker Manager starting all processes")
        for name in CHILD_SCRIPTS:
            self.start_process(name)

    def stop_all(self):
        logger.info("Worker Manager stopping all processes")
        self._stopping = True
        for name in list(self.popens):
            self.stop_process(name)
        from local_api import force_stop_local_api
        force_stop_local_api()
        self.registry.get("local_api").status = "stopped"

    # ---- health monitor ------------------------------------------------------

    def _read_state_file(self, name: str) -> dict | None:
        path = STATE_FILES.get(name)
        if not path or not path.exists():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return None

    def supervise_local_api(self):
        """Local API runs as an in-process thread, not a child process
        (docs/AIR_WORKER_PROCESS_MODEL.md §5) - if the thread has died
        (uncaught exception in the server loop), restart it in place.
        This satisfies the QA requirement '로컬 API 종료 후 자동 복구'."""
        rec = self.registry.get("local_api")
        if rec.status == "disabled":
            return
        if self._api_thread is None or not self._api_thread.is_alive():
            if rec.status == "running":
                logger.error("Local API thread died - restarting it")
                if not rec.record_crash(error="local_api thread died"):
                    logger.error(f"Local API DISABLED after repeated crashes: {rec.disabled_reason}")
                    return
            from local_api import run_local_api_thread
            self._api_thread = run_local_api_thread(self)
            rec.status = "running"
            rec.started_at = time.time()
            rec.last_heartbeat_at = time.time()
            rec.restart_count_total += 1

    def supervise_once(self):
        """One tick of the Health Monitor: check each managed child process
        for unexpected exit or stale heartbeat, apply bounded-restart policy
        (docs/AIR_WORKER_PROCESS_MODEL.md §3)."""
        self.supervise_local_api()
        for name in list(CHILD_SCRIPTS):
            rec = self.registry.get(name)
            if rec.status == "disabled":
                continue
            popen = self.popens.get(name)
            if not popen:
                continue

            exit_code = popen.poll()
            if exit_code is not None:
                # Process exited (crashed or was asked to stop).
                if self._stopping or rec.status == "stopped":
                    continue
                logger.error(f"'{name}' exited unexpectedly (code={exit_code})")
                can_restart = rec.record_crash(error=f"exit_code={exit_code}")
                if can_restart:
                    logger.info(f"Auto-restarting '{name}' (crash {len(rec.crash_timestamps)} in window)")
                    self.restart_process(name)
                else:
                    logger.error(f"'{name}' DISABLED after repeated crashes: {rec.disabled_reason}")
                continue

            state = self._read_state_file(name)
            if state:
                rec.last_heartbeat_at = state.get("heartbeat_at")
                if rec.status not in ("crashed", "disabled"):
                    rec.status = state.get("status", "running")
                if rec.last_heartbeat_at and (time.time() - rec.last_heartbeat_at) > HEARTBEAT_STALE_SECONDS:
                    logger.warning(f"'{name}' heartbeat stale ({time.time() - rec.last_heartbeat_at:.1f}s)")

        self._apply_resource_policy()

    def _apply_resource_policy(self):
        """docs/AIR_WORKER_RESOURCE_POLICY.md §2/§3, simplified for the skeleton:
        if the render worker currently reports a running job, pause Hermes by
        writing the pause flag file; otherwise clear it."""
        render_state = self._read_state_file("render_worker")
        render_busy = bool(render_state and render_state.get("current_job"))
        if render_busy and not PAUSE_FLAG_FILE.exists():
            logger.info("Render job active -> pausing Hermes new-job intake")
            PAUSE_FLAG_FILE.write_text("paused", encoding="utf-8")
        elif not render_busy and PAUSE_FLAG_FILE.exists():
            logger.info("Render queue idle -> resuming Hermes")
            PAUSE_FLAG_FILE.unlink(missing_ok=True)

    def run_supervisor_loop(self):
        logger.info("Health Monitor loop starting")
        while not self._stopping:
            try:
                self.supervise_once()
            except Exception as e:
                logger.error(f"Supervisor tick error (non-fatal, continuing): {e}")
            time.sleep(MANAGER_TICK_SECONDS)

    # ---- status snapshot for Local API ---------------------------------------

    def status_snapshot(self) -> dict:
        processes = self.registry.to_dict()
        for name in CHILD_SCRIPTS:
            state = self._read_state_file(name)
            if state:
                processes[name]["current_job"] = state.get("current_job")
                processes[name]["progress"] = state.get("progress")
        return {
            "worker_id": __import__("config").WORKER_ID,
            "processes": processes,
            "hermes_paused": PAUSE_FLAG_FILE.exists(),
        }


def main():
    manager = WorkerManager()
    manager.start_all()

    # Local API runs as an in-process thread (docs/AIR_WORKER_PROCESS_MODEL.md §5).
    from local_api import run_local_api_thread
    manager._api_thread = run_local_api_thread(manager)
    rec = manager.registry.get("local_api")
    rec.status = "running"
    rec.started_at = time.time()
    rec.last_heartbeat_at = time.time()

    try:
        manager.run_supervisor_loop()
    except KeyboardInterrupt:
        logger.info("Ctrl+C received, shutting down all processes")
    finally:
        manager.stop_all()
        logger.info("Worker Manager stopped")
        # [AIR-0227A QA finding] uvicorn.Server.run() started from a
        # non-main thread can leave the interpreter process alive after all
        # of our own threads/children have cleanly exited (observed during
        # this Task's QA pass - the Manager process itself lingered even
        # though every child process and the API thread had genuinely
        # stopped). A hard os._exit() here guarantees the process actually
        # terminates on program-exit, matching the QA requirement "프로그램
        # 종료 시 모든 하위 프로세스 정상 종료". This is a pragmatic
        # skeleton-stage workaround, not a real fix - see the completion
        # report for the recommendation to revisit Local API's threading
        # model in the next implementation phase.
        import os
        os._exit(0)


if __name__ == "__main__":
    main()
