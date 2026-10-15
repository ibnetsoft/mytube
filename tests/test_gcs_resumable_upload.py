import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'worker'))
import gcs_resumable_upload as upload

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
