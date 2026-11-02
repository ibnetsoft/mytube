import json
from unittest.mock import Mock

from worker.script_delivery_supervisor import Supervisor, eligible


def test_only_confirmed_new_standard_jobs_are_eligible():
    job = {'worker_id': 'worker', 'auto_delivery_requested': True, 'status': 'awaiting_approval'}
    request = {'mode': 'new', 'settings_confirmed': True, 'production_mode': 'standard', 'category_id': '13'}
    assert eligible(job, request, 'worker')
    for override in ({'settings_confirmed': False}, {'mode': 'repair'}, {'category_id': ''},
                     {'production_mode': 'moving_comic'}):
        assert not eligible(job, {**request, **override}, 'worker')
    for override in ({'status': 'canceled'}, {'published': True}, {'worker_id': 'other'},
                     {'auto_delivery_requested': False}):
        assert not eligible({**job, **override}, request, 'worker')


def test_supervisor_starts_once_and_retries_dead_child_with_backoff(tmp_path, monkeypatch):
    identity = 'a' * 32
    directory = tmp_path / identity
    directory.mkdir()
    (directory / 'job.json').write_text(json.dumps({'worker_id': 'worker', 'auto_delivery_requested': True,
                                                  'status': 'interrupted'}))
    (directory / 'request.json').write_text(json.dumps({'mode': 'new', 'settings_confirmed': True,
                                                      'production_mode': 'standard', 'category_id': '13'}))
    monkeypatch.setattr('worker.script_delivery_supervisor.active', lambda *_: None)
    now = [100]
    child = Mock(); child.poll.return_value = None
    launch = Mock(return_value=child)
    supervisor = Supervisor(tmp_path, tmp_path, 'worker', popen=launch, clock=lambda: now[0])
    supervisor.tick(); supervisor.tick()
    assert launch.call_count == 1
    child.poll.return_value = 1
    supervisor.tick(); supervisor.tick()
    assert launch.call_count == 1
    now[0] += 21
    supervisor.tick()
    assert launch.call_count == 2
    assert launch.call_args.args[0][-2:] == ['--job', identity]


def test_existing_exclusive_delivery_process_is_not_duplicated(tmp_path, monkeypatch):
    directory = tmp_path / ('b' * 32); directory.mkdir()
    (directory / 'job.json').write_text(json.dumps({'worker_id': 'worker', 'auto_delivery_requested': True, 'status': 'running'}))
    (directory / 'request.json').write_text(json.dumps({'mode': 'new', 'settings_confirmed': True, 'category_id': '13'}))
    monkeypatch.setattr('worker.script_delivery_supervisor.active', lambda *_: {'stage': 'running'})
    launch = Mock()
    Supervisor(tmp_path, tmp_path, 'worker', popen=launch).tick()
    launch.assert_not_called()
