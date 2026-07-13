"""
[AIR-0227B Stage 2/3/6/7] Worker Manager - the AIRWorker.exe entry point.

Changes from the AIR-0227A skeleton (worker/manager.py history):
  - Local API is now spawned as a real subprocess.Popen child
    (local_api_process.py), not an in-process thread - removes the root
    cause of the AIR-0227A finding that the Manager process sometimes
    wouldn't fully exit (uvicorn.Server.run() on a background thread).
  - Render Worker now runs the REAL pipeline (render_worker.py), not
    render_worker_mock.py.
  - A file-based command channel (worker/ipc.py) lets the now-separate
    Local API process ask the Manager to start/stop children, cancel a
    job, or shut everything down - polled once per supervisor tick.
  - graceful_shutdown() implements the full timed/logged 11-step shutdown
    protocol (docs/AIR_WORKER_SHUTDOWN_PROTOCOL.md) and REPLACES the
    os._exit(0) workaround entirely - normal process exit is now expected
    to actually terminate the interpreter, since nothing non-daemon is
    left running once graceful_shutdown() returns.
  - On startup, scans job_store for jobs abandoned by a previous crashed
    run (docs/AIR_WORKER_JOB_RECOVERY.md) before spawning any workers.
"""
import json
import os
import subprocess
import sys
import threading
import time
import uuid
from pathlib import Path

import job_store
from ipc import consume_command, pending_commands, read_command, write_result
from logging_setup import get_logger
from process_registry import ProcessRegistry
from shutdown_flag import clear_shutdown_flag, request_shutdown
from worker_config import (
    CANCEL_FLAG_DIR,
    COMMAND_DIR,
    HEARTBEAT_STALE_SECONDS,
    MANAGER_TICK_SECONDS,
    RESTART_BACKOFF_SECONDS,
    SHUTDOWN_GRACE_SECONDS,
    SHUTDOWN_JOB_ABORT_GRACE_SECONDS,
    STATE_DIR,
    WORKER_ID,
)

logger = get_logger("manager")

HERE = Path(__file__).resolve().parent
PYTHON = sys.executable
ENTRY_SCRIPT = HERE / "air_worker_entry.py"

# [AIR-0227E] Role names only, not .py paths - this used to map name ->
# sibling script path (HERE / "render_worker.py" etc), but that breaks under
# a frozen PyInstaller build: there is no python.exe to point at (sys.executable
# IS the frozen exe) and no standalone .py files on disk to Popen by path.
# Every child is now spawned by re-invoking the current running program with
# `--role <name>` instead - see _child_command() below and
# worker/air_worker_entry.py's docstring for the full rationale.
CHILD_SCRIPTS = ("render_worker", "hermes_worker", "local_api")  # hermes_worker still runs hermes_worker_mock.py under the hood - real Hermes connection out of this Task's scope
STATE_FILES = {
    "render_worker": STATE_DIR / "render_worker.json",
    "hermes_worker": STATE_DIR / "hermes_worker.json",
    "local_api": STATE_DIR / "local_api.json",
}
PAUSE_FLAG_FILE = STATE_DIR / "hermes_worker.pause"
MANAGER_STATUS_FILE = STATE_DIR / "manager_status.json"


def _child_command(role: str) -> list[str]:
    """[AIR-0227E] Build the Popen argv for child process `role`.

    Frozen (PyInstaller onefile AIRWorker.exe): sys.executable IS the exe
    itself, so re-invoke it directly with --role - there is no separate
    python.exe and no on-disk .py file to point at.

    From source (dev/QA): sys.executable is a real python.exe, so run it
    against air_worker_entry.py, same as always.

    Either way the target module's main() runs via
    worker/air_worker_entry.py's role dispatch, not by importing the child
    script directly."""
    if getattr(sys, "frozen", False):
        return [sys.executable, "--role", role]
    return [PYTHON, str(ENTRY_SCRIPT), "--role", role]


class WorkerManager:
    def __init__(self):
        self.registry = ProcessRegistry()
        self.popens: dict[str, subprocess.Popen] = {}
        self._lock = threading.Lock()
        self._stopping = False
        self._shutdown_thread: threading.Thread | None = None
        self._shutdown_started = threading.Event()
        # [AIR-0227C Stage 6] One instance id per Manager process start -
        # NEVER reused across restarts (docs/AIR_WORKER_LEASE_PROTOCOL.md:
        # "같은 PC라도 이전 instance의 만료되지 않은 작업을 임의로 완료하지
        # 않는다" - a fresh id each run means a Render Worker from a
        # previous Manager lifetime can never look like the current one).
        self.worker_instance_id = uuid.uuid4().hex
        logger.info(f"Worker instance id for this Manager run: {self.worker_instance_id}")
        for name in CHILD_SCRIPTS:
            self.registry.register(name)
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

            clear_shutdown_flag(name)  # a leftover flag from a previous stop would make the new instance exit immediately
            cmd = _child_command(name)
            logger.info(f"Starting '{name}' ({' '.join(cmd)})")
            # [AIR-0227B Stage 4 finding, not a regression introduced here]
            # services/video_service.py prints emoji/non-ASCII to stdout.
            # On a Windows console using a non-UTF-8 codepage (observed:
            # cp949 on this KR-locale machine) that raises
            # UnicodeEncodeError and crashes the Render Worker mid-job.
            # Forcing PYTHONIOENCODING=utf-8 for every child process is the
            # standard fix and doesn't require touching the existing
            # rendering pipeline's print statements.
            child_env = dict(os.environ, PYTHONIOENCODING="utf-8", AIRWORKER_INSTANCE_ID=self.worker_instance_id)
            popen = subprocess.Popen(cmd, cwd=str(HERE), env=child_env)
            self.popens[name] = popen
            rec.pid = popen.pid
            rec.status = "starting"
            rec.started_at = time.time()
            rec.restart_count_total += 1
            return True

    def _kill_process_tree(self, pid: int):
        """Windows-only guaranteed kill of a process AND all its descendants
        (e.g. an ffmpeg/moviepy child the Render Worker spawned) -
        docs/AIR_WORKER_JOB_RECOVERY.md §cancellation, docs/AIR_WORKER_SHUTDOWN_PROTOCOL.md.
        terminate()/kill() on the parent Popen handle alone does NOT
        guarantee this on Windows since a plain subprocess.run() child is
        not placed in a Job Object tied to the parent's lifetime."""
        try:
            result = subprocess.run(
                ["taskkill", "/PID", str(pid), "/T", "/F"],
                capture_output=True, text=True, timeout=15,
            )
            logger.info(f"taskkill /PID {pid} /T /F -> rc={result.returncode} {result.stdout.strip()} {result.stderr.strip()}")
        except Exception as e:
            logger.error(f"taskkill failed for pid={pid}: {e}")

    def stop_process(self, name: str, timeout: float = SHUTDOWN_GRACE_SECONDS, force_tree_kill: bool = False) -> bool:
        """Graceful-first, escalate-on-timeout. On Windows, Popen.terminate()
        is an unconditional TerminateProcess() that the child's Python
        signal handlers never see - see worker/shutdown_flag.py. The actual
        graceful path is: write the child's shutdown flag file, poll for it
        to self-exit within `timeout`; only escalate to terminate()/
        _kill_process_tree() if it hasn't."""
        with self._lock:
            popen = self.popens.get(name)
            rec = self.registry.get(name)
            if not popen or popen.poll() is not None:
                rec.status = "stopped"
                rec.pid = None
                return True
            pid = popen.pid
            logger.info(f"Stopping '{name}' (pid={pid}) - requesting graceful shutdown via flag file, timeout={timeout}s")
            request_shutdown(name)

            deadline = time.time() + timeout
            while time.time() < deadline:
                if popen.poll() is not None:
                    break
                time.sleep(0.2)

            if popen.poll() is None:
                logger.warning(f"'{name}' did not self-exit within {timeout}s of the shutdown flag, escalating to a hard kill")
                if force_tree_kill:
                    self._kill_process_tree(pid)
                else:
                    popen.terminate()
                try:
                    popen.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    logger.warning(f"'{name}' (pid={pid}) still alive after terminate(), escalating to process-tree kill")
                    self._kill_process_tree(pid)
                    try:
                        popen.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        logger.error(f"'{name}' (pid={pid}) still alive after taskkill /T /F - leaking")
            else:
                logger.info(f"'{name}' (pid={pid}) exited gracefully")

            clear_shutdown_flag(name)
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

    # ---- startup recovery (Stage 7) ----------------------------------------

    def run_startup_recovery(self):
        """Before spawning any workers, resolve jobs left ACTIVE by a
        previous Manager run that crashed/was force-killed
        (docs/AIR_WORKER_JOB_RECOVERY.md). alive_pid=None because no Render
        Worker of THIS Manager instance has run yet - every active job at
        this point is necessarily orphaned."""
        stale = job_store.find_stale_active_jobs(alive_pid=None)
        if not stale:
            logger.info("[RECOVERY] No stale active jobs found at startup")
            return
        logger.warning(f"[RECOVERY] Found {len(stale)} job(s) left active by a previous run")
        for job in stale:
            before = job["status"]
            recovered = job_store.mark_abandoned_and_recover(job)
            logger.warning(f"[RECOVERY] job {job['job_id']}: {before} -> ABANDONED -> {recovered['status']} ({recovered.get('error_message') or 'requeued or recovered output'})")

    # ---- command channel (Stage 2 - Local API is now a separate process) --

    def _handle_command(self, cmd: dict) -> dict:
        command = cmd.get("command")
        params = cmd.get("params", {})
        try:
            if command == "start_process":
                ok = self.start_process(params["name"])
                return {"success": ok}
            if command == "stop_process":
                ok = self.stop_process(params["name"])
                return {"success": ok}
            if command == "cancel_job":
                return self._cancel_job(params["job_id"])
            if command == "shutdown_all":
                # [Bug found via live shutdown QA, fixed here] This MUST NOT
                # be a daemon thread. run_supervisor_loop()'s while-loop
                # condition checks self._stopping (set at step 2 of
                # graceful_shutdown, before any child is actually stopped);
                # once it flips, the loop exits almost immediately and
                # main() falls through toward process exit. A daemon thread
                # is torn down the instant the interpreter's main thread
                # finishes - if graceful_shutdown() were still running in
                # one at that point, steps 5-13 (stopping render_worker and
                # local_api) would simply never execute. Observed exactly
                # this failure live: only steps 1-4 ever got logged.
                # main() now .join()s self._shutdown_thread before actually
                # letting the process end, so this only needs to be
                # non-daemon and tracked.
                if not self._shutdown_started.is_set():
                    self._shutdown_started.set()
                    self._shutdown_thread = threading.Thread(
                        target=lambda: self.graceful_shutdown("local_api /shutdown command"),
                        daemon=False, name="graceful-shutdown",
                    )
                    self._shutdown_thread.start()
                return {"success": True, "message": "Graceful shutdown initiated"}
            return {"success": False, "error": f"unknown command '{command}'"}
        except Exception as e:
            logger.error(f"Command '{command}' failed: {e}")
            return {"success": False, "error": str(e)}

    def poll_commands(self):
        for path in pending_commands():
            cmd = read_command(path)
            consume_command(path)
            if not cmd:
                continue
            logger.info(f"Command received: {cmd['command']} {cmd.get('params')}")
            result = self._handle_command(cmd)
            write_result(cmd["command_id"], result)

    def _cancel_job(self, job_id: str) -> dict:
        """docs/AIR_WORKER_JOB_RECOVERY.md cancellation policy:
        QUEUED -> cancel directly, no process touched.
        CLAIMED/PREPARING -> soft-cancel flag, Render Worker self-cancels at
          its PREPARING checkpoint; if it wins the race into RENDERING first,
          fall through to the hard path below.
        RENDERING/UPLOADING -> no cancellation hook exists in the wrapped
          pipeline, so the only guaranteed way to actually stop it (ffmpeg
          child included) is a full process-tree kill of the Render Worker,
          followed by a fresh restart for future jobs."""
        job = job_store.get_job(job_id)
        if not job:
            return {"success": False, "error": "job not found"}
        status = job["status"]

        if status == job_store.QUEUED:
            job_store.transition(job_id, job_store.CANCELED, reason="cancelled while queued")
            return {"success": True, "result": "cancelled_queued"}

        if status in (job_store.CLAIMED, job_store.PREPARING):
            (CANCEL_FLAG_DIR / f"{job_id}.cancel").write_text("cancel", encoding="utf-8")
            for _ in range(20):  # up to ~4s for the worker to reach/honor its checkpoint
                time.sleep(0.2)
                refreshed = job_store.get_job(job_id)
                if refreshed["status"] == job_store.CANCELED:
                    return {"success": True, "result": "cancelled_soft_checkpoint"}
                if refreshed["status"] == job_store.RENDERING:
                    break  # lost the race - fall through to hard kill
            status = job_store.get_job(job_id)["status"]
            if status not in (job_store.RENDERING, job_store.UPLOADING):
                return {"success": False, "error": f"job left in unexpected status {status} during soft-cancel"}

        if status in (job_store.RENDERING, job_store.UPLOADING):
            popen = self.popens.get("render_worker")
            if popen and popen.poll() is None:
                logger.warning(f"Hard-cancelling job {job_id}: killing render_worker process tree (pid={popen.pid})")
                self._kill_process_tree(popen.pid)
            job_store.transition(job_id, job_store.CANCELED, reason="render worker process tree killed to cancel active render")
            self.registry.get("render_worker").status = "stopped"
            self.registry.get("render_worker").pid = None
            self.start_process("render_worker")
            return {"success": True, "result": "cancelled_hard_kill"}

        return {"success": False, "error": f"job already in terminal status {status}, nothing to cancel"}

    # ---- health monitor ------------------------------------------------------

    def _read_state_file(self, name: str) -> dict | None:
        path = STATE_FILES.get(name)
        if not path or not path.exists():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return None

    def supervise_once(self):
        """One tick of the Health Monitor: check each managed child process
        for unexpected exit or stale heartbeat, apply bounded-restart policy
        (docs/AIR_WORKER_PROCESS_MODEL.md §3), poll the command channel, and
        publish a status snapshot for Local API to read."""
        self.poll_commands()

        for name in list(CHILD_SCRIPTS):
            rec = self.registry.get(name)
            if rec.status == "disabled":
                continue
            popen = self.popens.get(name)
            if not popen:
                continue

            exit_code = popen.poll()
            if exit_code is not None:
                if self._stopping or rec.status == "stopped":
                    continue
                logger.error(f"'{name}' exited unexpectedly (code={exit_code})")
                if name == "render_worker":
                    self._recover_jobs_owned_by(popen.pid)
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
        self._publish_status()

    def _recover_jobs_owned_by(self, dead_pid: int):
        """[Stage 7] Called the moment we notice the Render Worker died
        unexpectedly - immediately resolve whatever job it was holding
        instead of waiting for the next Manager restart.

        [Bug found via live crash QA, fixed here] This does NOT filter by
        matching job['worker_pid'] == dead_pid. render_worker.py records its
        own os.getpid() as worker_pid, but on this Windows Python/venv
        setup the pid subprocess.Popen() returns to the Manager and the pid
        the child sees for itself differ (the venv python.exe launcher
        re-execs into a child process with its own pid) - so that
        equality check silently matched nothing and jobs stayed stuck in
        RENDERING forever after a real crash, discovered only by actually
        force-killing a render worker mid-job and watching it fail to
        recover. Fix: since the Manager only ever runs one Render Worker
        Process at a time, at the exact moment we're handling its crash
        there is by definition no live process that could legitimately own
        any job still in an ACTIVE status - so every such job found here
        IS orphaned, regardless of which literal pid it recorded. This
        mirrors run_startup_recovery()'s alive_pid=None semantics, applied
        immediately instead of only at the next Manager start."""
        stale = job_store.find_stale_active_jobs(alive_pid=None)
        for job in stale:
            recovered = job_store.mark_abandoned_and_recover(job)
            logger.warning(f"[RECOVERY] job {job['job_id']} (owning Render Worker pid={dead_pid} crashed): {job['status']} -> {recovered['status']}")

    def _apply_resource_policy(self):
        """docs/AIR_WORKER_RESOURCE_POLICY.md §2/§3: if the render worker
        currently reports a running job, pause Hermes by writing the pause
        flag file; otherwise clear it."""
        render_state = self._read_state_file("render_worker")
        render_busy = bool(render_state and render_state.get("current_job"))
        if render_busy and not PAUSE_FLAG_FILE.exists():
            logger.info("Render job active -> pausing Hermes new-job intake")
            PAUSE_FLAG_FILE.write_text("paused", encoding="utf-8")
        elif not render_busy and PAUSE_FLAG_FILE.exists():
            logger.info("Render queue idle -> resuming Hermes")
            PAUSE_FLAG_FILE.unlink(missing_ok=True)

    def _publish_status(self):
        snapshot = self.status_snapshot()
        snapshot["written_at"] = time.time()
        MANAGER_STATUS_FILE.write_text(json.dumps(snapshot, ensure_ascii=False), encoding="utf-8")

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
            "worker_id": WORKER_ID,
            "worker_instance_id": self.worker_instance_id,
            "processes": processes,
            "hermes_paused": PAUSE_FLAG_FILE.exists(),
        }

    # ---- graceful shutdown (Stage 3) -----------------------------------------

    def graceful_shutdown(self, reason: str):
        """Timed, logged, 11-step shutdown protocol - docs/AIR_WORKER_SHUTDOWN_PROTOCOL.md.
        Replaces AIR-0227A's os._exit(0) workaround: Local API is now its
        own subprocess (no more uvicorn-in-a-thread), so once every child is
        confirmed stopped and the supervisor loop has returned, normal
        interpreter exit is expected to actually terminate this process."""
        t0 = time.time()
        step = 0

        def log_step(msg):
            nonlocal step
            step += 1
            logger.info(f"[SHUTDOWN step {step}/11] {msg} (+{time.time() - t0:.2f}s)")

        log_step(f"SHUTDOWN_INITIATED reason='{reason}'")
        self._stopping = True
        log_step("Manager marked shutting_down, supervisor loop will exit after this tick")

        MANAGER_STATUS_FILE.write_text(
            json.dumps({"worker_id": WORKER_ID, "status": "shutting_down", "written_at": time.time()}, ensure_ascii=False),
            encoding="utf-8",
        )
        log_step("Published shutting_down status for Local API/CLI to reflect")

        log_step("Stopping Hermes Worker (low priority, safe to interrupt immediately)")
        self.stop_process("hermes_worker", timeout=SHUTDOWN_GRACE_SECONDS)

        render_state = self._read_state_file("render_worker")
        job_active = bool(render_state and render_state.get("current_job"))
        log_step(f"Render Worker job_active={job_active}")

        render_timeout = SHUTDOWN_GRACE_SECONDS + (SHUTDOWN_JOB_ABORT_GRACE_SECONDS if job_active else 0)
        log_step(f"Signalling Render Worker to stop, granting up to {render_timeout}s "
                  f"({'honors PREPARING checkpoint only, cannot abort a live encode' if job_active else 'no active job'})")
        popen = self.popens.get("render_worker")
        pid_before = popen.pid if popen else None
        self.stop_process("render_worker", timeout=render_timeout, force_tree_kill=True)

        if job_active and pid_before:
            self._recover_jobs_owned_by(pid_before)
        log_step("Render Worker stop resolved (any interrupted job handed to recovery)")

        log_step("Stopping Local API process last (serves this very shutdown response)")
        self.stop_process("local_api", timeout=SHUTDOWN_GRACE_SECONDS)

        leftover = []
        for name, popen in self.popens.items():
            if popen.poll() is None:
                leftover.append((name, popen.pid))
        if leftover:
            logger.error(f"[SHUTDOWN] {len(leftover)} leftover PID(s) after stop sequence: {leftover}")
        log_step(f"Leftover PID check: {len(leftover)} process(es) still alive: {leftover}")

        cleaned = 0
        for f in COMMAND_DIR.glob("*.json"):
            f.unlink(missing_ok=True)
            cleaned += 1
        if PAUSE_FLAG_FILE.exists():
            PAUSE_FLAG_FILE.unlink()
        log_step(f"Cleaned up {cleaned} stale command file(s) and the Hermes pause flag")

        log_step(f"SHUTDOWN_COMPLETE total_elapsed={time.time() - t0:.2f}s leftover_pids={len(leftover)}")


def main():
    manager = WorkerManager()
    manager.run_startup_recovery()
    manager.start_all()

    def _signal_shutdown(signum, frame):
        if not manager._shutdown_started.is_set():
            manager._shutdown_started.set()
            manager.graceful_shutdown(f"signal {signum}")

    import signal
    signal.signal(signal.SIGINT, _signal_shutdown)
    try:
        signal.signal(signal.SIGTERM, _signal_shutdown)
    except (AttributeError, ValueError):
        pass

    try:
        manager.run_supervisor_loop()
    except KeyboardInterrupt:
        if not manager._shutdown_started.is_set():
            manager._shutdown_started.set()
            manager.graceful_shutdown("KeyboardInterrupt")

    # run_supervisor_loop() returns as soon as self._stopping flips (set at
    # graceful_shutdown step 2, before any child has actually been asked to
    # stop yet) - if shutdown was triggered via the command channel it is
    # still running on its own thread at this point. Wait for it so the
    # process genuinely does not exit until all 13 steps have completed -
    # this is what makes removing os._exit() safe.
    if manager._shutdown_thread is not None:
        manager._shutdown_thread.join()

    logger.info("Worker Manager main() returning - process should now exit normally (no os._exit)")


if __name__ == "__main__":
    main()
