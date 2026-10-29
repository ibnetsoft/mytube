from types import SimpleNamespace
from unittest.mock import patch
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'worker'))

import worker.ae_highlight_worker as ae


def test_forwarded_script_keeps_shared_session_open(tmp_path):
    jsx = tmp_path / 'scene.jsx'
    jsx.write_text('// scene')
    project = tmp_path / 'scene.aep'
    commands = []
    process = SimpleNamespace(poll=lambda: 0)
    def launch(command, **kwargs):
        commands.append(command)
        return process
    def finish(_):
        project.write_bytes(b'project')
        jsx.with_suffix('.status.txt').write_text('success|' + str(project))
    with patch.object(ae.subprocess, 'Popen', side_effect=launch), patch.object(ae.time, 'sleep', side_effect=finish), patch.object(ae, 'continue_crash_recovery', return_value=False), patch.object(ae, '_request_afterfx_close') as close:
        ae._run_afterfx_script(tmp_path / 'AfterFX.exe', jsx, project, timeout=10)
    assert '-m' not in commands[0]
    assert '-r' in commands[0]
    close.assert_not_called()


def test_relative_script_is_forwarded_as_absolute_path(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    jsx = Path('scene.jsx')
    jsx.write_text('// actual script')
    project = tmp_path / 'scene.aep'
    commands = []
    def launch(command, **kwargs):
        commands.append(command)
        project.write_bytes(b'project')
        jsx.with_suffix('.status.txt').write_text('success|' + str(project))
        return SimpleNamespace(poll=lambda: 0)
    with patch.object(ae.subprocess, 'Popen', side_effect=launch):
        ae._run_afterfx_script(Path('AfterFX.exe'), jsx, Path('scene.aep'), timeout=3)
    assert commands[0][-1] == str(jsx.resolve())
    assert Path(commands[0][-1]).is_absolute()
