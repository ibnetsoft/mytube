import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'worker'))
import gcs_resumable_upload as upload
import pytest


@pytest.fixture(autouse=True)
def shared_transport(monkeypatch):
    class Client:
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def post(self,*args,**kwargs):return upload.requests.post(*args,**kwargs)
        def put(self,*args,**kwargs):return upload.requests.put(*args,**kwargs)
    monkeypatch.setattr(upload.requests,'Session',Client)

def test_completed_upload_is_reused_without_sending_bytes_again(tmp_path,monkeypatch):
    file=tmp_path/'video.mp4';file.write_bytes(b'completed video')
    sends=[]
    class Response:
        def __init__(self,status,headers=None): self.status_code=status;self.headers=headers or {}
        def raise_for_status(self): pass
        def json(self): return {'size':str(file.stat().st_size)}
    monkeypatch.setattr(upload.requests,'post',lambda *a,**kw:Response(200,{'Location':'https://example.invalid/session'}))
    completed=False
    def put(*args,**kwargs):
        nonlocal completed
        if kwargs['headers']['Content-Range'].startswith('bytes */'):
            return Response(200 if completed else 308)
        sends.append(kwargs['data']);completed=True;return Response(200)
    monkeypatch.setattr(upload.requests,'put',put)
    upload.upload_resumable(file,'bucket','video','video/mp4','not-a-real-token')
    upload.upload_resumable(file,'bucket','video','video/mp4','not-a-real-token')
    assert sends==[b'completed video']


def test_large_file_uses_bounded_chunks_and_exact_acknowledged_offsets(tmp_path,monkeypatch):
    file=tmp_path/'large.mp4';contents=b'a'*(2*1024*1024+17);file.write_bytes(contents)
    offset=0;sizes=[]
    class Response:
        def __init__(self,status,headers=None):self.status_code=status;self.headers=headers or {}
        def raise_for_status(self):pass
        def json(self):return {'size':str(len(contents))}
    monkeypatch.setattr(upload.requests,'post',lambda *a,**kw:Response(200,{'Location':'https://example.invalid/session'}))
    def put(*args,**kwargs):
        nonlocal offset
        span=kwargs['headers']['Content-Range']
        if span.startswith('bytes */'):return Response(308,{'Range':f'bytes=0-{offset-1}'} if offset else {})
        data=kwargs['data'];assert len(data)<=1024*1024
        assert span==f'bytes {offset}-{offset+len(data)-1}/{len(contents)}'
        assert data==contents[offset:offset+len(data)]
        sizes.append(len(data));offset+=len(data)
        return Response(200 if offset==len(contents) else 308,{'Range':f'bytes=0-{offset-1}'})
    monkeypatch.setattr(upload.requests,'put',put)
    upload.upload_resumable(file,'bucket','video','video/mp4','not-a-real-token')
    assert sizes==[1024*1024,1024*1024,17]
