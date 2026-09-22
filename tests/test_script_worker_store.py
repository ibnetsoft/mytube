import copy
import json
from pathlib import Path
import sys
import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from worker import codex_local_console as console
from worker.script_worker_store import StoreUnavailable, ScriptStore


class MemoryStore:
    def __init__(self):
        self.rows = {}
        self.offline = False

    def save(self, bundle):
        if self.offline:
            raise StoreUnavailable('offline')
        self.rows[bundle['job']['id']] = copy.deepcopy(bundle)

    def get(self, identity):
        return copy.deepcopy(self.rows[identity])

    def active(self):
        if self.offline:
            raise StoreUnavailable('offline')
        return [{'id': k, 'worker_id': b['job']['worker_id']} for k, b in self.rows.items()
                if b['job']['status'] in ('queued', 'running')]

    def enrich_media(self, rows):
        from worker.script_worker_media import unknown_media
        for row in rows:
            row['media'] = unknown_media()


@pytest.fixture
def setup(tmp_path, monkeypatch):
    store = MemoryStore()
    jobs = console.Jobs(tmp_path, store)
    monkeypatch.setattr(console, 'jobs', jobs)
    monkeypatch.setattr(console, 'store', store)
    # Exercise lifecycle synchronously without running a real model.
    monkeypatch.setattr(jobs.pool, 'submit', lambda *args: None)
    client = TestClient(console.app, base_url=console.ORIGIN, headers={'X-Codex-Local': console.TOKEN})
    yield jobs, store, client
    jobs.pool.shutdown()


def request():
    return console.StartRequest(mode='new', title='보존할 대본', category='story')


def test_result_and_approval_survive_missing_local_folder(setup, tmp_path, monkeypatch):
    jobs, store, client = setup
    from worker import codex_local_workflow
    candidate = {'script': '전체 대본', 'structure': {'scenes': [{'text': '전체 대본'}]},
                 'remaining': ['이미지 제작'], 'sfx_cues': []}
    monkeypatch.setattr(codex_local_workflow, 'produce', lambda *a, **kw: candidate)
    row = jobs.start(request(), None)
    jobs.run(row['id'], request(), None)
    assert store.rows[row['id']]['candidate'] == candidate
    assert store.rows[row['id']]['job']['status'] == 'awaiting_approval'
    restored = console.Jobs(tmp_path / 'another-machine', store)
    try:
        monkeypatch.setattr(console, 'jobs', restored)
        response = client.get('/api/jobs/' + row['id'])
        assert response.status_code == 200
        assert response.json()['script'] == '전체 대본'
        response = client.post('/api/jobs/' + row['id'] + '/approve', json={'candidate_hash': console.digest(candidate)})
        assert response.status_code == 200
        assert store.rows[row['id']]['job']['status'] == 'approved_pending_repair'
        assert store.rows[row['id']]['job']['published'] is False
    finally:
        restored.pool.shutdown()


def test_start_requires_cloud_and_does_not_execute_offline(setup, monkeypatch):
    jobs, store, client = setup
    store.offline = True
    calls = []
    monkeypatch.setattr(jobs.pool, 'submit', lambda *a: calls.append(a))
    response = client.post('/api/jobs', json=request().model_dump())
    assert response.status_code == 502
    assert not calls and not jobs.rows


def test_failed_upload_keeps_result_and_manual_sync_recovers(setup, monkeypatch):
    jobs, store, client = setup
    from worker import codex_local_workflow
    def produce(*a, **kw):
        store.offline = True
        return {'script': '네트워크 장애 중 완성한 대본'}
    monkeypatch.setattr(codex_local_workflow, 'produce', produce)
    row = jobs.start(request(), None)
    jobs.run(row['id'], request(), None)
    assert jobs.rows[row['id']]['status'] == 'awaiting_approval'
    assert jobs.rows[row['id']]['sync_status'] == 'pending'
    assert jobs.bundle(row['id'])['candidate']['script']
    store.offline = False
    assert client.post('/api/jobs/' + row['id'] + '/sync', json={}).status_code == 200
    assert store.rows[row['id']]['candidate']['script']
    assert jobs.rows[row['id']]['sync_status'] == 'synced'


def test_retry_retains_old_failure_and_links_new_attempt(setup):
    jobs, store, client = setup
    original = jobs.start(request(), None)
    jobs.update(original['id'], status='failed')
    response = client.post('/api/jobs/' + original['id'] + '/retry', json={})
    assert response.status_code == 200
    retry = response.json()
    assert retry['id'] != original['id'] and retry['retry_of'] == original['id']
    assert store.rows[original['id']]['job']['status'] == 'failed'
    assert client.post('/api/jobs/' + retry['id'] + '/retry', json={}).status_code == 409


def test_restart_reconciles_only_this_worker(setup, tmp_path):
    jobs, store, _ = setup
    row = jobs.start(request(), None)
    restarted = console.Jobs(tmp_path / 'empty-cache', store)
    try:
        restarted.connect()
        assert store.rows[row['id']]['job']['status'] == 'interrupted'
    finally:
        restarted.pool.shutdown()
    store.rows[row['id']]['job'].update(status='running', worker_id='another-worker')
    other = console.Jobs(tmp_path / 'other-cache', store)
    try:
        other.connect()
        assert store.rows[row['id']]['job']['status'] == 'running'
    finally:
        other.pool.shutdown()


def test_legacy_current_script_is_not_a_historical_snapshot(setup, monkeypatch):
    _, store, client = setup
    monkeypatch.setattr(store, 'legacy', lambda i: {'id': i, 'job_type': 'script_generate',
        'status': 'failed', 'payload': {'topic_queue_id': '42', 'topic': '과거 제목'}, 'result_payload': None}, raising=False)
    monkeypatch.setattr(console, 'source', lambda *a: {'script': '현재 수정된 대본'})
    data = client.get('/api/history/legacy/valid').json()
    assert data['script'] == '현재 수정된 대본'
    assert '스냅샷이 아닙니다' in data['result_origin']
    assert data['job']['status'] == 'failed'
    assert data['source_link'] == {'kind': 'topic', 'id': '42'}


def test_history_pagination_filter_and_error_are_explicit(setup, monkeypatch):
    _, store, client = setup
    capture = []
    monkeypatch.setattr(store, 'history', lambda *args: capture.append(args) or {'items': [], 'total': 0}, raising=False)
    assert client.get('/api/history?page=2&origin=legacy&q=hello&state=failed').status_code == 200
    assert capture == [(2, 'legacy', 'hello', 'failed')]
    assert client.get('/api/history?state=invalid').status_code == 400
    def fail(*args):
        raise StoreUnavailable('연결 실패')
    monkeypatch.setattr(store, 'history', fail)
    assert client.get('/api/history').status_code == 502


def test_store_only_writes_dedicated_table_and_never_leaks_transport_error(monkeypatch):
    import requests
    monkeypatch.setenv('SUPABASE_SERVICE_ROLE_KEY', 'secret')
    monkeypatch.setenv('NEXT_PUBLIC_SUPABASE_URL', 'https://example.supabase.co')
    def fail(*args, **kwargs):
        raise requests.ConnectionError('secret URL or response')
    monkeypatch.setattr(requests, 'request', fail)
    with pytest.raises(StoreUnavailable) as exc:
        ScriptStore().request('GET', 'script_worker_jobs')
    assert 'secret' not in str(exc.value)
    with pytest.raises(ValueError):
        ScriptStore().get('../escape')


def test_restart_uploads_finished_offline_result_instead_of_marking_interrupted(setup, tmp_path):
    jobs, store, _ = setup
    row = jobs.start(request(), None)
    store.offline = True
    console.write_json(jobs.root / row['id'] / 'candidate.json', {'script': '완성 대본'})
    jobs.update(row['id'], status='awaiting_approval', stage='완성')
    store.offline = False
    restarted = console.Jobs(jobs.root, store)
    try:
        restarted.connect()
        assert store.rows[row['id']]['job']['status'] == 'awaiting_approval'
        assert store.rows[row['id']]['candidate']['script'] == '완성 대본'
    finally:
        restarted.pool.shutdown()


def test_cached_foreign_running_job_is_not_interrupted_on_restart(setup, tmp_path):
    jobs, store, _ = setup
    row = jobs.start(request(), None)
    store.rows[row['id']]['job'].update(worker_id='another-worker', status='running')
    cache = console.Jobs(tmp_path / 'foreign-cache', store)
    cache.restore(store.get(row['id']))
    cache.pool.shutdown()
    restarted = console.Jobs(cache.root, store)
    try:
        restarted.connect()
        assert restarted.rows[row['id']]['status'] == 'running'
        assert store.rows[row['id']]['job']['status'] == 'running'
    finally:
        restarted.pool.shutdown()
