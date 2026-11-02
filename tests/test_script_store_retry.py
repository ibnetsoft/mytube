import requests
import pytest

from worker import script_worker_store as module


@pytest.fixture(autouse=True)
def config(monkeypatch):
    monkeypatch.setenv('NEXT_PUBLIC_SUPABASE_URL', 'https://example.invalid')
    monkeypatch.setenv('SUPABASE_SERVICE_ROLE_KEY', 'test-key')
    monkeypatch.setattr(module.time, 'sleep', lambda _: None)


def response():
    result = requests.Response()
    result.status_code = 200
    result._content = b'[]'
    return result


@pytest.mark.parametrize('method,params,prefer', [
    ('GET', None, 'count=exact'),
    ('POST', {'on_conflict': 'id'}, 'resolution=merge-duplicates,return=minimal'),
])
def test_timeout_retries_only_safe_operations(monkeypatch, method, params, prefer):
    calls = []
    def request(*args, **kwargs):
        calls.append(1)
        if len(calls) < 3:
            raise requests.ReadTimeout('temporary')
        return response()
    monkeypatch.setattr(module.requests, 'request', request)
    assert module.ScriptStore().request(method, 'items', params=params, prefer=prefer)[0] == []
    assert len(calls) == 3


def test_timeout_does_not_retry_non_idempotent_write(monkeypatch):
    calls = []
    def request(*args, **kwargs):
        calls.append(1)
        raise requests.ReadTimeout('ambiguous')
    monkeypatch.setattr(module.requests, 'request', request)
    with pytest.raises(module.StoreUnavailable):
        module.ScriptStore().request('POST', 'items', body={'value': 1})
    assert len(calls) == 1
