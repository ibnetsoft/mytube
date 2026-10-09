"""An active Adobe render must drain before the Manager kills its worker."""
from __future__ import annotations

import pathlib
import sys
import threading
import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "worker"))


class _Clock:
    def __init__(self):
        self.now = 0.0

    def monotonic(self):
        return self.now

    def sleep(self, seconds):
        self.now += seconds


class _Popen:
    pid = 4321

    def __init__(self, clock, exit_at=float("inf")):
        self.clock = clock
        self.exit_at = exit_at
        self.killed = False

    def poll(self):
        return 0 if self.killed or self.clock.now >= self.exit_at else None

    def wait(self, timeout):
        self.killed = True
        return 0


def _manager_with_worker(monkeypatch, role, clock, popen):
    import manager as module

    worker_manager = module.WorkerManager()
    worker_manager.popens[role] = popen
    worker_manager.registry.get(role).status = "running"
    monkeypatch.setattr(module.time, "monotonic", clock.monotonic)
    monkeypatch.setattr(module.time, "sleep", clock.sleep)
    monkeypatch.setattr(module, "request_shutdown", lambda _name: None)
    monkeypatch.setattr(module, "clear_shutdown_flag", lambda _name: None)
    return module, worker_manager


@pytest.mark.parametrize("role", ["ae_highlight_worker", "ae_mouth_worker"])
def test_ae_active_scene_finishes_after_old_grace_without_hard_kill(monkeypatch, role):
    clock = _Clock()
    popen = _Popen(clock, exit_at=15)
    module, worker_manager = _manager_with_worker(monkeypatch, role, clock, popen)
    monkeypatch.setattr(module, "SHUTDOWN_MEDIA_DRAIN_SECONDS", 30)
    monkeypatch.setattr(worker_manager, "_read_state_file", lambda _name: {
        "current_job": {"scene": 1} if clock.now < 13 else None,
    })
    hard_kills = []
    monkeypatch.setattr(worker_manager, "_kill_process_tree", lambda pid: hard_kills.append(pid))

    assert worker_manager.stop_process(role, timeout=2, force_tree_kill=True,
                                       drain_current_job=True)
    assert clock.now >= 15  # the former 13-second deadline has passed
    assert hard_kills == []
    assert worker_manager.registry.get(role).status == "stopped"


def test_hung_premiere_export_is_bounded_and_tree_killed(monkeypatch):
    clock = _Clock()
    popen = _Popen(clock)
    module, worker_manager = _manager_with_worker(monkeypatch, "premiere_final_worker", clock, popen)
    monkeypatch.setattr(module, "SHUTDOWN_MEDIA_DRAIN_SECONDS", 10)
    monkeypatch.setattr(worker_manager, "_read_state_file", lambda _name: {"current_job": {"project": 1}})
    hard_kills = []

    def kill(pid):
        hard_kills.append(pid)
        popen.killed = True

    monkeypatch.setattr(worker_manager, "_kill_process_tree", kill)

    assert worker_manager.stop_process("premiere_final_worker", timeout=2, force_tree_kill=True,
                                       drain_current_job=True)
    assert 10 <= clock.now < 11
    assert hard_kills == [popen.pid]


def test_media_stop_command_returns_while_current_job_drains(monkeypatch):
    import manager as module

    worker_manager = module.WorkerManager()
    entered = threading.Event()
    release = threading.Event()

    def stop(_name, **kwargs):
        entered.set()
        assert kwargs["drain_current_job"] is True
        assert release.wait(2)
        return True

    monkeypatch.setattr(worker_manager, "stop_process", stop)
    response = worker_manager._handle_command({
        "command": "stop_process", "params": {"name": "ae_highlight_worker"},
    })
    assert response == {"success": True, "status": "stopping"}
    assert entered.wait(2)
    assert "ae_highlight_worker" in worker_manager._draining_roles
    assert worker_manager.start_process("ae_highlight_worker") is False
    class Exited:
        pid = 9876

        def poll(self):
            return 1

    worker_manager.popens["ae_highlight_worker"] = Exited()
    monkeypatch.setattr(worker_manager, "poll_commands", lambda: None)
    monkeypatch.setattr(worker_manager, "_apply_resource_policy", lambda: None)
    monkeypatch.setattr(worker_manager, "_publish_status", lambda: None)
    restarts = []
    monkeypatch.setattr(worker_manager, "restart_process", lambda name: restarts.append(name))
    worker_manager.supervise_once()
    assert restarts == []
    stop_thread = worker_manager._media_stop_threads["ae_highlight_worker"]
    release.set()
    stop_thread.join(2)
    assert "ae_highlight_worker" not in worker_manager._draining_roles


def test_global_shutdown_includes_premiere_worker(monkeypatch, tmp_path):
    import manager as module

    worker_manager = module.WorkerManager()
    monkeypatch.setattr(module, "MANAGER_STATUS_FILE", tmp_path / "status.json")
    command_dir = tmp_path / "commands"
    command_dir.mkdir()
    monkeypatch.setattr(module, "COMMAND_DIR", command_dir)
    monkeypatch.setattr(module, "PAUSE_FLAG_FILE", tmp_path / "pause.flag")
    monkeypatch.setattr(worker_manager, "_read_state_file", lambda _name: None)
    stopped = []
    monkeypatch.setattr(worker_manager, "stop_process", lambda name, **kwargs: stopped.append((name, kwargs)) or True)

    worker_manager.graceful_shutdown("test")

    assert "premiere_final_worker" in [name for name, _kwargs in stopped]
    premiere_kwargs = next(kwargs for name, kwargs in stopped if name == "premiere_final_worker")
    assert premiere_kwargs["drain_current_job"] is True
    assert premiere_kwargs["force_tree_kill"] is True


def test_active_premiere_export_pauses_new_hermes_jobs(monkeypatch, tmp_path):
    import manager as module

    worker_manager = module.WorkerManager()
    pause_flag = tmp_path / "hermes.pause"
    monkeypatch.setattr(module, "PAUSE_FLAG_FILE", pause_flag)
    monkeypatch.setattr(module, "ALWAYS_ON_CHILD_SCRIPTS", ("premiere_final_worker", "hermes_worker"))
    monkeypatch.setattr(worker_manager, "_read_state_file", lambda name: {
        "current_job": {"project_id": "p1"} if name == "premiere_final_worker" else None,
    })

    worker_manager._apply_resource_policy()

    assert pause_flag.is_file()
