"""Focused checks for unattended After Effects crash handling."""
from __future__ import annotations

import pathlib
import sys
import types

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "worker"))


class _Control:
    def __init__(self, label: str, kind: str = "Text"):
        self.label = label
        self.element_info = types.SimpleNamespace(control_type=kind)
        self.invoked = False

    def window_text(self) -> str:
        return self.label

    def invoke(self) -> None:
        self.invoked = True


class _Window(_Control):
    def __init__(self, pid: int, title: str, controls: list[_Control]):
        super().__init__(title)
        self.pid = pid
        self.controls = controls

    def process_id(self) -> int:
        return self.pid

    def descendants(self) -> list[_Control]:
        return self.controls


def _desktop(monkeypatch, windows):
    import ae_recovery

    monkeypatch.setattr(ae_recovery, "os", types.SimpleNamespace(name="nt"))
    monkeypatch.setattr(ae_recovery, "_is_afterfx_process", lambda pid: pid == 101)
    monkeypatch.setitem(sys.modules, "pywinauto", types.SimpleNamespace(
        Desktop=lambda **_kwargs: types.SimpleNamespace(windows=lambda: windows)
    ))
    return ae_recovery


def test_recovery_clicks_only_exact_ae_continue_button(monkeypatch):
    unrelated = _Control("Continue", "Button")
    ae_button = _Control("계속", "Button")
    ae_recovery = _desktop(monkeypatch, [
        _Window(99, "Crash Recovery Options", [unrelated]),
        _Window(101, "Adobe After Effects", [
            _Control("충돌 복구 옵션"), ae_button, _Control("환경 설정", "Button")
        ]),
    ])
    assert ae_recovery.continue_crash_recovery() is True
    assert ae_button.invoked is True
    assert unrelated.invoked is False


def test_recovery_missing_continue_is_actionable(monkeypatch):
    ae_recovery = _desktop(monkeypatch, [
        _Window(101, "Crash Recovery Options", [_Control("Cancel", "Button")])
    ])
    with pytest.raises(ae_recovery.AeRecoveryError, match="Continue button is unavailable"):
        ae_recovery.continue_crash_recovery()


def test_aerender_keeps_failure_log_and_reports_exit(monkeypatch, tmp_path):
    import ae_highlight_worker as worker

    monkeypatch.setattr(worker, "continue_crash_recovery", lambda: False)
    target = tmp_path / "render.mp4"
    command = [sys.executable, "-c", "import sys; print('AE render diagnostic'); sys.exit(7)", str(target)]
    with pytest.raises(worker.AeWorkerError, match="exit=7") as error:
        worker._run_checked(command, timeout=5)
    assert "AE render diagnostic" in str(error.value)
    assert target.with_suffix(".aerender.log").is_file()


def test_aerender_timeout_stops_child_and_reports_log(monkeypatch, tmp_path):
    import ae_highlight_worker as worker

    monkeypatch.setattr(worker, "continue_crash_recovery", lambda: False)
    target = tmp_path / "slow.mp4"
    command = [sys.executable, "-c", "import time; time.sleep(10)", str(target)]
    with pytest.raises(worker.AeWorkerError, match="timed out") as error:
        worker._run_checked(command, timeout=0.2)
    assert "slow.aerender.log" in str(error.value)


def test_project_creation_waits_for_fresh_stable_aep(monkeypatch, tmp_path):
    import ae_highlight_worker as worker

    project = tmp_path / "project.aep"
    project.write_bytes(b"old" * 400)
    jsx = tmp_path / "create.jsx"
    jsx.write_text("", encoding="utf-8")
    clock = types.SimpleNamespace(value=0.0)
    monkeypatch.setattr(worker.time, "monotonic", lambda: clock.value)
    monkeypatch.setattr(worker.time, "sleep", lambda seconds: setattr(clock, "value", clock.value + seconds))
    monkeypatch.setattr(worker, "continue_crash_recovery", lambda: False)

    class _Process:
        def __init__(self):
            self.polls = 0

        def poll(self):
            self.polls += 1
            if self.polls == 1:
                project.write_bytes(b"new" * 700)
            return 0

    process = _Process()
    monkeypatch.setattr(worker.subprocess, "Popen", lambda *_args, **_kwargs: process)
    worker._run_afterfx_script(tmp_path / "AfterFX.exe", jsx, project, timeout=10)
    assert project.read_bytes().startswith(b"new")
    assert clock.value >= 2
