import json
import pathlib
import sys
import threading
import time
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / 'worker'))
from std_project_assets import load_project_assets
from ae_mouth_runtime import Heartbeat, instance_lock


def test_every_asset_is_loaded_including_original_video_after_row_1000():
    rows = [{'id': str(i)} for i in range(1265)]
    rows[1032] = {'id': 'original-video-scene-5'}
    offsets = []
    def request(method, url, headers, params):
        assert params['order'] == 'created_at.desc,id.desc'
        assert params['status'] == 'in.(uploaded,assigned)'
        start = int(params['offset']); offsets.append(start)
        return SimpleNamespace(json=lambda: rows[start:start + int(params['limit'])])
    assert load_project_assets(request, 'db', {}, 'p') == rows
    assert offsets == [0, 500, 1000]


def test_page_failure_does_not_return_incomplete_sources():
    def request(method, url, headers, params):
        if int(params['offset']):
            raise RuntimeError('network failure')
        return SimpleNamespace(json=lambda: [{'id': 1}] * 500)
    with pytest.raises(RuntimeError):
        load_project_assets(request, 'db', {}, 'p')


def test_heartbeat_continues_during_blocking_render_and_clears_job_on_exit(tmp_path):
    path = tmp_path / 'state.json'
    with Heartbeat(path, 'instance', interval=.01) as state:
        state.update(status='running', current_job={'id': 'job', 'scene_number': 12})
        initial = json.loads(path.read_text())['heartbeat_at']
        deadline = time.monotonic() + 2
        while json.loads(path.read_text())['heartbeat_at'] <= initial and time.monotonic() < deadline:
            threading.Event().wait(.02)
        latest = json.loads(path.read_text())
        assert latest['heartbeat_at'] > initial
        assert latest['current_job_id'] == 'job'
    assert json.loads(path.read_text())['status'] == 'stopped'
    assert json.loads(path.read_text())['current_job'] is None


def test_role_and_profiles_dispatch_mouth_main(monkeypatch):
    import air_worker_entry as entry
    import manager
    import worker_config as config
    calls = []
    monkeypatch.setitem(sys.modules, 'ae_mouth_worker', SimpleNamespace(main=lambda: calls.append('main')))
    entry._dispatch('ae_mouth_worker', False)
    assert calls == ['main']
    assert 'ae_mouth_worker' in manager.CHILD_SCRIPTS
    assert 'ae_mouth_worker' in manager.MEDIA_WORKERS
    assert manager.STATE_FILES['ae_mouth_worker'].name == 'ae_mouth_worker.json'
    for profile in ['full', 'render_only']:
        assert 'ae_mouth_worker' in config.PROFILE_CHILD_SCRIPTS[profile]
    assert 'ae_mouth_worker' not in config.PROFILE_CHILD_SCRIPTS['content_only']


def test_single_instance_lock_releases_after_exit(tmp_path):
    lock = tmp_path / 'worker.lock'
    with instance_lock(lock):
        with pytest.raises(OSError):
            with instance_lock(lock):
                pytest.fail('second instance acquired the lock')
    with instance_lock(lock):
        pass


def test_supervised_mouth_once_never_runs_coordinate_analysis(monkeypatch, tmp_path):
    import ae_mouth_worker as worker
    calls = []
    monkeypatch.setattr(worker.worker_config, 'STATE_DIR', tmp_path)
    monkeypatch.setitem(worker.worker_config.LOG_FILES, 'ae_mouth_worker', tmp_path / 'mouth.log')
    monkeypatch.setattr(worker, 'process_one', lambda **kw: calls.append('mouth') or False)
    monkeypatch.setitem(sys.modules, 'ae_speaker_coordinates', SimpleNamespace(process_one=lambda **kw: pytest.fail('AE role must not claim coordinate jobs')))
    monkeypatch.setattr(sys, 'argv', ['entry', '--role', 'ae_mouth_worker', '--once', '--mouth-only'])
    worker.main()
    assert calls == ['mouth']
    assert json.loads((tmp_path / 'ae_mouth_worker.json').read_text())['status'] == 'stopped'
