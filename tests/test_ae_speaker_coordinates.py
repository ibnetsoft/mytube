import sys
from pathlib import Path
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'worker'))
from ae_mouth import assess_dialogue, visible_speakers

def test_saved_assignments_need_no_model_call():
    class Runner:
        def _stage(self,*args): raise AssertionError('Saved assignments must not be reclassified')
    rows=[{'index':0,'text':'はい','scene_number':19,'kind':'dialogue','speaker':'娘'},
          {'index':1,'text':'語り','scene_number':20,'kind':'narration','speaker':''},
          {'index':2,'text':'不明','scene_number':21,'kind':'','speaker':''}]
    result=assess_dialogue(Runner(),'saved',{'subtitles':rows})
    assert [r['kind'] for r in result]==['dialogue','narration','uncertain']
    assert result[0]['speaker']=='娘'

def test_mouth_must_be_inside_verified_face():
    row={'speaker':'娘','status':'visible','confidence':.99,'reason':'visual evidence','face_box':[.2,.2,.6,.6],'mouth_box':[.4,.4,.45,.43]}
    assert visible_speakers({'speakers':[row]},['娘'])[0]['face_box']==row['face_box']
    with pytest.raises(ValueError,match='inside'):
        visible_speakers({'speakers':[{**row,'face_box':[.1,.1,.3,.3]}]},['娘'])

@pytest.fixture
def coordinate_job(monkeypatch, tmp_path):
    import copy
    import ae_highlight_worker as ae
    import ae_speaker_coordinates as worker
    import codex_content_runner as runner
    from PIL import Image
    scene = {'number':19,'text':'dialogue','rows':[{'kind':'dialogue','speaker':'娘','text':'はい'}],
             'image':{'id':'image','metadata':{'gcs_bucket':'bucket','gcs_path':'scene.png'}}}
    job = {'id':'job','project_id':'project','updated_at':'old', 'metadata':{
        'kind':'ae_speaker_coordinates','state':'queued','fingerprint':'test',
        'input':{'scenes':[scene], 'cast':{},'cast_key':'{}'},'results':[]}}
    saved=[]
    def request(method,url,headers,params=None,json=None):
        if method=='GET':
            if params.get('select')=='metadata': data=[]
            else:
                assert 'updated_at.lt.' in params['or'], 'Fresh processing jobs must not be reclaimed'
                data=[copy.deepcopy(job)]
        else:
            if 'updated_at' in params: assert params['updated_at']=='eq.old'
            else: assert params['metadata->>worker_token']=='eq.'+job['metadata']['worker_token']
            job.update(copy.deepcopy(json));saved.append(copy.deepcopy(job['metadata']));data=[copy.deepcopy(job)]
        return type('Response',(),{'json':lambda self:data})()
    monkeypatch.setattr(ae,'_supabase',lambda:('https://example.invalid',{}))
    monkeypatch.setattr(ae,'_request',request)
    monkeypatch.setattr(ae,'ROOT',tmp_path)
    monkeypatch.setattr(ae,'_download_gcs_file',lambda ref,path:Image.new('RGB',(1280,720)).save(path))
    def stage(self,identity,name,context,task):
        image=Path(context['_local_image_paths'][0])
        assert image.is_file() and image.is_relative_to(tmp_path/'output/codex-local-console')
        return {'speakers':[{'speaker':'娘','status':'visible','confidence':.99,'reason':'source inspected',
                             'face_box':[.2,.2,.6,.6],'mouth_box':[.4,.4,.45,.43]}]}
    monkeypatch.setattr(runner.CodexStagedContentRunner,'_stage',stage)
    return worker,job,saved


def test_coordinate_job_claims_analyzes_and_publishes_validated_scene(coordinate_job):
    worker,job,saved=coordinate_job
    assert worker.process_one()
    assert saved[0]['state']=='processing'
    assert any(row.get('current_scene')==19 for row in saved)
    assert job['metadata']['state']=='ready'
    assert len(job['metadata']['results'])==1
    assert job['metadata']['results'][0]['speakers'][0]['face_box']==[.2,.2,.6,.6]


def test_retry_preserves_completed_scenes(coordinate_job,monkeypatch):
    import codex_content_runner as runner
    worker,job,saved=coordinate_job
    completed={'number':19,'speakers':[{'speaker':'娘','status':'offscreen'}]}
    job['metadata']['results']=[completed]
    monkeypatch.setattr(runner.CodexStagedContentRunner,'_stage',lambda *args:pytest.fail('Completed scenes must be preserved'))
    worker.process_one()
    assert job['metadata']['results']==[completed]


def test_analysis_failure_is_visible_and_never_counted_as_ready(coordinate_job,monkeypatch):
    import codex_content_runner as runner
    worker,job,saved=coordinate_job
    def fail(*args): raise ValueError('Speaker visibility is uncertain')
    monkeypatch.setattr(runner.CodexStagedContentRunner,'_stage',fail)
    worker.process_one()
    assert job['metadata']['state']=='needs_review'
    assert job['metadata']['results']==[]
    assert 'uncertain' in job['metadata']['error']


def test_worker_does_not_overwrite_reclaimed_job(coordinate_job,monkeypatch):
    import ae_highlight_worker as ae
    worker,job,saved=coordinate_job
    original=ae._request
    def lost(method,url,headers,**kwargs):
        if method=='PATCH' and 'metadata->>worker_token' in kwargs['params']:
            return type('Response',(),{'json':lambda self:[]})()
        return original(method,url,headers,**kwargs)
    monkeypatch.setattr(ae,'_request',lost)
    with pytest.raises(worker.LeaseLost): worker.process_one()
    assert len(saved)==1 and saved[0]['state']=='processing'


def test_uncertain_scene_does_not_block_following_scenes(coordinate_job,monkeypatch):
    import copy
    import codex_content_runner as runner
    worker,job,saved=coordinate_job
    second=copy.deepcopy(job['metadata']['input']['scenes'][0]);second['number']=20
    job['metadata']['input']['scenes'].append(second)
    original=runner.CodexStagedContentRunner._stage
    def stage(self,identity,*args):
        assert self.config.timeout_seconds <= 180
        if '-19-' in identity: raise ValueError('Visible speaker confidence needs review')
        return original(self,identity,*args)
    monkeypatch.setattr(runner.CodexStagedContentRunner,'_stage',stage)
    worker.process_one()
    assert job['metadata']['state']=='needs_review'
    assert [r['number'] for r in job['metadata']['results']]==[20]
    assert [r['number'] for r in job['metadata']['failures']]==[19]
    assert job['metadata']['current_scene'] is None


def test_retry_uses_fresh_analysis_identity_not_cached_rejected_response(coordinate_job,monkeypatch):
    import codex_content_runner as runner
    worker,job,saved=coordinate_job
    ids=[]
    def stage(self,identity,*args):
        ids.append(identity)
        raise ValueError('confidence needs review')
    monkeypatch.setattr(runner.CodexStagedContentRunner,'_stage',stage)
    worker.process_one()
    job['updated_at']='old';job['metadata']['state']='queued'
    worker.process_one()
    assert len(ids)==2 and ids[0]!=ids[1]
