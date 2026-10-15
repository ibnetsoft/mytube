import hashlib
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'worker'))
import render_asset_cache as cache

def test_interrupted_download_resumes_and_next_render_uses_identical_cached_bytes(tmp_path, monkeypatch):
    data = b'a' * (1024 * 1024) + b'b' * 19
    calls = []
    class Response:
        status_code = 206
        headers = {'ETag':'same','x-goog-generation':'1','Content-Length':str(len(data))}
        def __enter__(self): return self
        def __exit__(self,*args): pass
        def raise_for_status(self): pass
        def iter_content(self,size):
            if len(calls)==1:
                yield data[:1024*1024]
                raise cache.requests.ConnectionError('interrupted')
            yield data[1024*1024:]
    monkeypatch.setattr(cache.requests,'head',lambda *args,**kwargs:Response())
    def get(*args,**kwargs):
        calls.append(kwargs['headers']['Range']);return Response()
    monkeypatch.setattr(cache.requests,'get',get)
    monkeypatch.setattr(cache.time,'sleep',lambda *_:None)
    source={'gcs_bucket':'b','gcs_path':'p','gcs_signed_url':'https://test.invalid/file'}
    sha=hashlib.sha256(data).hexdigest()
    cache.download_cached(source,tmp_path/'first',None,tmp_path/'cache',sha)
    cache.download_cached(source,tmp_path/'second',None,tmp_path/'cache',sha)
    assert calls==['bytes=0-','bytes=1048576-']
    assert (tmp_path/'second').read_bytes()==data
