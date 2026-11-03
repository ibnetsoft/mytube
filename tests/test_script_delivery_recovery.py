import copy
import importlib.util
import json
import subprocess
import sys
import types
from pathlib import Path

import pytest

from worker.script_delivery_recovery import acquire_lock, checkpoint_package, complete_registration


def test_exclusive_lock_is_real_and_released(tmp_path):
    path = tmp_path/'supervisor.lock'
    lock = acquire_lock(path)
    code = ('from pathlib import Path; from worker.script_delivery_recovery import acquire_lock; '
            'acquire_lock(Path(__import__("sys").argv[1]))')
    result = subprocess.run([sys.executable, '-c', code, str(path)], capture_output=True)
    assert result.returncode != 0
    lock.close()
    result = subprocess.run([sys.executable, '-c', code, str(path)], capture_output=True)
    assert result.returncode == 0, result.stderr


def test_checkpoint_reuses_only_exact_inputs_and_detects_corruption(tmp_path):
    calls = []
    def build():
        calls.append(1)
        return {'script': 'saved final narration'}
    path = tmp_path/'prepared.json'
    for _ in range(2):
        assert checkpoint_package(path, 'a'*32, {'request': 1}, build)['script']
    assert len(calls) == 1
    checkpoint_package(path, 'a'*32, {'request': 2}, build)
    assert len(calls) == 2
    saved = json.loads(path.read_text()); saved['package']['script'] = 'changed'
    path.write_text(json.dumps(saved))
    with pytest.raises(ValueError, match='checkpoint bytes changed'):
        checkpoint_package(path, 'a'*32, {'request': 2}, build)


@pytest.mark.parametrize('committed', [False, True])
@pytest.mark.parametrize('fail_at', [1, 2])
@pytest.mark.parametrize('local_result', [False, True])
def test_delivery_recovers_lost_save_without_regeneration_and_finishes(tmp_path, monkeypatch, committed, fail_at, local_result):
    identity = 'a'*32
    root = tmp_path/'output/codex-local-console'/identity
    root.mkdir(parents=True)
    request = {'mode': 'new', 'language': 'ko', 'title': 'Test', 'settings_confirmed': True}
    (root/'request.json').write_text(json.dumps(request))
    package = {'script': 'one\n\ntwo', 'structure': {'scenes': [
        {'scene_number': 1, 'scene_text': 'one'}, {'scene_number': 2, 'scene_text': 'two'}]}}
    if local_result:
        (root/'candidate.json').write_text(json.dumps(package))
        (root/'job.json').write_text(json.dumps({'id': identity, 'status': 'awaiting_approval'}))
    calls = {'produce': 0, 'prepare': 0, 'publish': 0}
    class Store:
        def __init__(self):
            self.bundle = {'job': {'id': identity, 'status': 'running' if local_result else 'interrupted', 'storage_revision': 1},
                           'request': request, 'candidate': {}}
            self.saved = 0
        def get(self, _): return copy.deepcopy(self.bundle)
        def save(self, bundle):
            self.saved += 1
            assert bundle['job']['storage_revision'] == self.bundle['job']['storage_revision']
            if self.saved == fail_at and not committed:
                raise TimeoutError('write never reached DB')
            self.bundle = copy.deepcopy(bundle)
            self.bundle['job']['storage_revision'] += 1
            if self.saved == fail_at:
                raise TimeoutError('commit succeeded; reply lost')
    store = Store()
    spec = importlib.util.spec_from_file_location('continue_delivery_test', Path(__file__).resolve().parents[1]/'scripts/continue_script_topic.py')
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    monkeypatch.setattr(module, 'ROOT', tmp_path)
    monkeypatch.setattr(module, 'ScriptStore', lambda: store)
    monkeypatch.setattr(module, 'CodexStagedContentRunner', lambda: object())
    def produce(*args):
        calls['produce'] += 1
        return copy.deepcopy(package)
    monkeypatch.setitem(sys.modules, 'worker.codex_local_workflow', types.SimpleNamespace(produce=produce))
    def prepare(*args):
        calls['prepare'] += 1
        return copy.deepcopy(package)
    monkeypatch.setattr(module, 'complete_candidate', prepare)
    monkeypatch.setitem(sys.modules, 'worker.codex_subtitle_translation', types.SimpleNamespace(
        translate_blocks=lambda runner, job, blocks, language: [{**b, 'translated_text': 'translated'} for b in blocks]))
    def publish(*args):
        calls['publish'] += 1
        assert store.bundle['candidate']['script'] == package['script']
        return {'source_job_id': identity, 'topic_id': 42}
    monkeypatch.setattr(module, 'publish_topic', publish)
    sleeps = []
    def sleep(delay):
        sleeps.append(delay)
        assert len(sleeps) < 5, (root/'delivery/last-error.json').read_text()
    monkeypatch.setattr(module.time, 'sleep', sleep)
    monkeypatch.setattr(sys, 'argv', ['continue_script_topic.py', '--job', identity])
    module.main()
    expected_publishes = 2 if fail_at == 2 and not committed else 1
    assert calls == {'produce': 0 if local_result else 1, 'prepare': 1, 'publish': expected_publishes}
    assert store.bundle['job']['status'] == 'completed'
    assert store.bundle['job']['published'] is True
    assert json.loads((root/'delivery/status.json').read_text())['status'] == 'completed'
    module.main()
    assert calls['publish'] == expected_publishes


def test_cancel_during_completion_is_preserved(tmp_path):
    class Store:
        def get(self, _): return {'job': {'status': 'canceled'}}
        def save(self, _): pytest.fail('Canceled job must not be written')
    with pytest.raises(ValueError, match='canceled'):
        complete_registration(Store(), 'a'*32, {'script': 'x'}, {'topic_id': 1}, tmp_path)
