import json
from pathlib import Path
import sys

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from worker import codex_local_console as console


@pytest.fixture
def client():
    return TestClient(console.app, base_url=console.ORIGIN,
                      headers={'X-Codex-Local': console.TOKEN})


def test_boundary(client):
    assert client.get('/health').json()['legacy_dashboard'] is False
    assert client.get('/api/status').status_code == 200
    assert client.get('/api/status', headers={'X-Codex-Local': ''}).status_code == 401
    assert client.get('/api/status', headers={'Host': 'evil.test:3003'}).status_code == 403
    assert client.get('/', headers={'Sec-Fetch-Site': 'cross-site'}).status_code == 403
    assert client.post('/api/jobs', headers={'Origin': 'https://evil.test'}, json={}).status_code == 403
    assert 'frame-ancestors' in client.get('/').headers['content-security-policy']


def test_catalog_pagination_and_no_script_leak(client, monkeypatch):
    captured = {}
    def fake(table, **params):
        captured.update(params)
        return [{'id': 3197, 'topic': '<script>test</script>', 'status': 'pending',
                 'pregenerated_script': 'private full script', 'pregenerated_structure': {'scenes': [{}]}}], 81
    monkeypatch.setattr(console, 'db_read', fake)
    response = client.get('/api/catalog?page=1&q=3197')
    assert response.status_code == 200
    data = response.json()
    assert captured['offset'] == 40
    assert data['total'] == 81 and data['has_more']
    assert data['items'][0]['has_script']
    assert 'private full script' not in response.text
    assert 'id.eq.3197' in captured['or']


def test_read_failure_not_empty_success(client, monkeypatch):
    def fail(*args, **kwargs):
        raise RuntimeError('secret must not leak')
    monkeypatch.setattr(console, 'db_read', fail)
    response = client.get('/api/catalog')
    assert response.status_code == 502
    assert 'secret' not in response.text


def test_approval_requires_exact_source_and_candidate(tmp_path):
    jobs = console.Jobs(tmp_path)
    job_id = 'a' * 32
    candidate = {'script': 'approved version'}
    candidate_hash = console.digest(candidate)
    jobs.rows[job_id] = {'id': job_id, 'status': 'awaiting_approval', 'candidate_hash': candidate_hash}
    console.write_json(tmp_path / job_id / 'candidate.json', candidate)
    console.write_json(tmp_path / job_id / 'source.json', {'fingerprint': 'original'})
    with pytest.raises(ValueError):
        jobs.approve(job_id, 'wrong', {'fingerprint': 'original'})
    with pytest.raises(ValueError):
        jobs.approve(job_id, candidate_hash, {'fingerprint': 'changed'})
    jobs.approve(job_id, candidate_hash, {'fingerprint': 'original'})
    assert jobs.rows[job_id]['status'] == 'approved_pending_repair'
    assert jobs.rows[job_id]['approved_hash'] == candidate_hash
    jobs.pool.shutdown()


def test_restart_does_not_auto_resume(tmp_path):
    console.write_json(tmp_path / 'old' / 'job.json', {'id': 'old', 'status': 'running'})
    jobs = console.Jobs(tmp_path)
    assert jobs.rows['old']['status'] == 'interrupted'
    jobs.pool.shutdown()


def test_duplicate_start_blocked(tmp_path):
    jobs = console.Jobs(tmp_path)
    jobs.rows['active'] = {'status': 'running'}
    with pytest.raises(ValueError):
        jobs.start(console.StartRequest(mode='new', title='test', category='story'), None)
    jobs.pool.shutdown()


def test_submission_is_protected_and_background_is_not_final():
    row = {'id': 'p', 'status': 'submitted', 'employee_email': 'owner@example.com',
           'project_payload': {'script': 'text'}, 'progress_payload': {'thumbnail_bg_url': 'https://example.com/bg.png'}}
    result = console.summary(row, 'project')
    assert result['protected']
    assert result['thumbnail'] == '배경 준비'


def test_no_legacy_execution_or_db_writes():
    code = (ROOT / 'worker/codex_local_console.py').read_text(encoding='utf-8')
    workflow = (ROOT / 'worker/codex_local_workflow.py').read_text(encoding='utf-8')
    assert 'requests.post(' not in code and 'requests.patch(' not in code
    assert 'import hermes_worker' not in code + workflow
    assert 'script_only=True' in workflow
    assert 'improve_for_listener' in workflow and 'validate_dialogue' in workflow


def test_untrusted_text_not_html():
    js = (ROOT / 'worker/codex_console/app.js').read_text(encoding='utf-8')
    assert 'innerHTML' not in js
    assert 'textContent' in js
