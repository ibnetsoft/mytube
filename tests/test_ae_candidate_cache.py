import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'worker'))
from ae_candidate_cache import load_candidates


def test_persistent_cache_downloads_only_changed_candidates(tmp_path):
    state = {'version': 'v1', 'payload_reads': 0, 'present': True}
    class Response:
        def __init__(self, data): self.data = data
        def json(self): return self.data
    def request(method, url, headers, json):
        assert method == 'POST'
        if url.endswith('manifest'):
            return Response([{'id': '1', 'version': state['version'], 'topic': 'fresh title'}] if state['present'] else [])
        state['payload_reads'] += 1
        return Response([{'id': '1', 'version': state['version'], 'pregenerated_structure': {'script': state['version']}}])
    def read(): return load_candidates(request, 'https://example.test', {}, 'topic', 20, tmp_path)
    assert read()[0]['pregenerated_structure']['script'] == 'v1'
    assert read()[0]['topic'] == 'fresh title'
    assert state['payload_reads'] == 1
    state['version'] = 'v2'
    assert read()[0]['pregenerated_structure']['script'] == 'v2'
    assert state['payload_reads'] == 2
    state['present'] = False
    assert read() == []
