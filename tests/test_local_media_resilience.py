import json
from pathlib import Path
from unittest.mock import Mock, patch

import requests
import worker.local_media_supervisor as supervisor
import worker.local_media_dashboard as dashboard
import worker.ae_highlight_worker as ae


def test_windows_status_lock_retries_and_survives(tmp_path):
    real_replace = Path.replace
    attempts = []
    def replace(path, target):
        attempts.append(1)
        if len(attempts) < 3:
            raise PermissionError()
        return real_replace(path, target)
    with patch.object(supervisor, 'HOME', tmp_path), patch.object(supervisor.time, 'sleep'):
        with patch.object(Path, 'replace', replace):
            assert supervisor.write_state({'status': 'working'})
        assert len(attempts) == 3
        assert json.loads((tmp_path / 'status.json').read_text())['status'] == 'working'
        with patch.object(Path, 'replace', side_effect=PermissionError()):
            assert supervisor.write_state({'status': 'idle'}) is False


def test_read_retries_connection_failure_but_create_does_not():
    success = Mock(ok=True, status_code=200)
    with patch.object(ae.requests, 'request', side_effect=[requests.ConnectionError(), success]) as call, patch.object(ae.time, 'sleep'):
        assert ae._request('GET', 'https://test.invalid', {}) is success
        assert call.call_count == 2
    with patch.object(ae.requests, 'request', side_effect=requests.ConnectionError()) as call:
        try:
            ae._request('POST', 'https://test.invalid', {})
        except requests.ConnectionError:
            pass
        else:
            raise AssertionError('Creation must not silently retry')
        assert call.call_count == 1


def test_generated_and_excluded_counts_are_separate():
    result = dashboard.summarize({'id': 'job', 'metadata': {
        'kind': 'ae_mouth_job', 'input': {'scenes': [1, 2, 3]},
        'results': [{'status': 'skipped'}, {'status': 'review_pending', 'asset_id': 'video'}],
    }})
    assert (result['generated'], result['skipped'], result['total']) == (1, 1, 3)
    assert dashboard.group('draft') == 'review'


def test_failed_refresh_preserves_last_good_snapshot():
    snapshot = dashboard.Snapshot()
    with patch.object(dashboard, 'fetch_jobs', return_value=[{'id': 'keep'}]):
        original = snapshot.read()
    snapshot.next_poll = 0
    with patch.object(dashboard, 'fetch_jobs', side_effect=ConnectionError()):
        failed = snapshot.read()
    assert failed['jobs'] == original['jobs']
    assert failed['updated_at'] == original['updated_at']
    assert failed['error']
