import hashlib
import io
from PIL import Image

def original_bytes():
    output=io.BytesIO(); Image.new('RGB',(4,4),'red').save(output,format='PNG'); return output.getvalue()
from pathlib import Path
from worker import wuxia_scene_review_queue as queue

class Store:
    def __init__(self, sha):
        self.job={'id':'00000000-0000-4000-8000-000000000001','claim_token':'00000000-0000-4000-8000-000000000002',
            'project_id':'p','scene_id':'s','scene_number':8,'project_updated_at':'v1','scene_updated_at':'v2',
            'source_sha256':hashlib.sha256(original_bytes()).hexdigest(),'candidate_sha256':sha,'candidate_bucket':'b','candidate_path':'candidate'}
        self.calls=[];self.changed=False
    def request(self, method, table, **kwargs):
        self.calls.append((method,table,kwargs))
        if table=='rpc/claim_std_scene_image_review':return [self.job],None
        if table=='rpc/touch_std_scene_image_review':return True,None
        if table=='std_projects':return [{'updated_at':'changed' if self.changed else 'v1','status':'in_progress','submitted_at':None}],None
        if table=='std_project_scenes':return [{'updated_at':'v2','metadata':{'source_image_sha256':self.job['source_sha256'],'scene_id':'S008','gcs_bucket':'b','gcs_path':'original'}}],None
        if table=='rpc/apply_std_scene_image_review':return {'success':True},None
        return [],None


def test_review_queue_applies_only_reviewed_candidate(tmp_path,monkeypatch):
    import worker.ae_highlight_worker as ae
    payload=b'candidate';store=Store(hashlib.sha256(payload).hexdigest())
    monkeypatch.setattr(queue,'REVIEW_ROOT',tmp_path)
    monkeypatch.setattr(ae,'_download_gcs_file',lambda ref,target:Path(target).write_bytes(payload if ref.path=='candidate' else original_bytes()))
    monkeypatch.setattr(queue,'review_local_candidate',lambda *args,**kw:{'contract':'test'})
    monkeypatch.setattr(queue,'review_scene_continuity',lambda *args,**kw:{'verdict':'pass'})
    assert queue.process_one(store,runner=object()) is True
    assert any(row[1]=='rpc/apply_std_scene_image_review' for row in store.calls)


def test_review_queue_preserves_changed_scene(tmp_path,monkeypatch):
    store=Store('b'*64);store.changed=True
    assert queue.process_one(store,runner=object()) is True
    assert not any(row[1]=='rpc/apply_std_scene_image_review' for row in store.calls)
    assert any(row[0]=='PATCH' and row[2]['body']['status']=='conflict' for row in store.calls)


def test_review_tool_failure_is_queued_with_backoff(tmp_path,monkeypatch):
    import worker.ae_highlight_worker as ae
    payload=b'candidate';store=Store(hashlib.sha256(payload).hexdigest())
    monkeypatch.setattr(queue,'REVIEW_ROOT',tmp_path)
    monkeypatch.setattr(ae,'_download_gcs_file',lambda ref,target:Path(target).write_bytes(payload if ref.path=='candidate' else original_bytes()))
    def unavailable(*args,**kwargs): raise RuntimeError('tool unavailable')
    monkeypatch.setattr(queue,'review_scene_continuity',unavailable)
    import pytest
    with pytest.raises(RuntimeError): queue.process_one(store,runner=object())
    patches=[row[2]['body'] for row in store.calls if row[0]=='PATCH']
    assert len(patches)==1 and patches[0]['status']=='queued' and patches[0].get('next_attempt_at')
    assert not any(row[1]=='rpc/apply_std_scene_image_review' for row in store.calls)


def test_review_queue_accepts_explicit_cut_when_scene_id_is_absent(tmp_path,monkeypatch):
    import worker.ae_highlight_worker as ae
    payload=b'candidate';store=Store(hashlib.sha256(payload).hexdigest())
    base=store.request
    def request(method,table,**kwargs):
        result=base(method,table,**kwargs)
        if table=='std_project_scenes' and method=='GET':
            result[0][0]['metadata']['scene_id']=None
            result[0][0]['metadata']['cut_id']='C008'
        return result
    store.request=request
    monkeypatch.setattr(queue,'REVIEW_ROOT',tmp_path)
    monkeypatch.setattr(ae,'_download_gcs_file',lambda ref,target:Path(target).write_bytes(payload if ref.path=='candidate' else original_bytes()))
    seen=[]
    def continuity(*args,**kwargs): seen.append(kwargs['scene_id']); return {'verdict':'pass'}
    def anatomy(*args,**kwargs): seen.append(kwargs['scene']['scene_id']); return {'contract':'test'}
    monkeypatch.setattr(queue,'review_scene_continuity',continuity)
    monkeypatch.setattr(queue,'review_local_candidate',anatomy)
    assert queue.process_one(store,runner=object()) is True
    assert seen==['C008','C008']
