"""Worker contract tests: actual media checks stay active; model calls are injected."""
import copy
import json
import shutil
import sys
from pathlib import Path
from unittest.mock import patch
import pytest
from PIL import Image,ImageDraw
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'worker'))
from worker import wuxia_mouth_preparation as w
from ae_mouth import digest


def fixture(tmp_path):
    image=tmp_path/'original.png'
    Image.new('RGB',(400,200),'tan').save(image)
    state={'asset_id':'STATE','sha256':digest(image),'gcs_bucket':'test','gcs_path':str(image)}
    graph={'kind':'speech_bubble','state_asset_id':'STATE','speaker':'hero','text':'안녕.','block_id':'B1'}
    structure={'main_character':{'id':'hero','name':'서진'},'wuxia_ae_package':{'contract':'wuxia_still_ae_episode/v1','scenes':[{'scene_id':'E01_S01','states':[state],'graphics':[graph]}]}}
    return image,structure


class Runner:
    def _stage(self,*args):raise AssertionError('Inject actual-source locator, never external API')


def test_future_only_and_explicit_disable():
    p={'structure':{'wuxia_ae_package':{'contract':'wuxia_still_ae_episode/v1'}}}
    assert w.enable_new_package(p)['structure']['wuxia_mouth_policy']['auto_prepare']
    p['structure']['wuxia_mouth_policy']={'enabled':False}
    assert w.enable_new_package(p)['structure']['wuxia_mouth_policy']=={'enabled':False}
    assert 'wuxia_mouth_policy' not in w.enable_new_package({'structure':{}})['structure']


def test_zero_is_normal_without_generating_or_uploading(tmp_path,monkeypatch):
    image,s=fixture(tmp_path);monkeypatch.setattr(w,'ROOT',tmp_path/'cache')
    with patch('ae_mouth.locate_speakers',return_value=[{'speaker':'hero','status':'offscreen','reason':'Back facing camera'}]),patch('prepared_mouth_layers.prepare_scene',return_value={'entries':[]}) as generate:
        report=w.prepare_art(s,'test',lambda ref,p:shutil.copyfile(image,p),lambda *a:pytest.fail('zero must not upload'),runner=Runner())
        assert report['report']['state']=='not_required'
        assert report['report']['selection_complete'] is True
        assert generate.call_args.args[1]['speakers']==[]
        assert report['states'][0]['art']==[]


def test_missing_image_and_tool_failure_are_not_zero(tmp_path,monkeypatch):
    image,s=fixture(tmp_path);monkeypatch.setattr(w,'ROOT',tmp_path/'cache')
    s['wuxia_ae_package']['scenes'][0]['states'][0].pop('gcs_path')
    with pytest.raises(RuntimeError,match='waiting_images'):
        w.prepare_art(s,'test',None,None,runner=Runner())
    image,s=fixture(tmp_path)
    with patch('ae_mouth.locate_speakers',side_effect=RuntimeError('CLI unavailable')):
        with pytest.raises(RuntimeError,match='CLI unavailable'):
            w.prepare_art(s,'test',lambda ref,p:shutil.copyfile(image,p),None,runner=Runner())
    with pytest.raises(RuntimeError,match='not complete'):
        w.prepare_art({'wuxia_ae_package':{'scenes':[]}},'test',None,None,runner=Runner())


def test_small_or_occluded_face_never_generates():
    assert not w.eligible({'status':'visible','face_box':[.1,.1,.4,.2],'mouth_box':[.15,.15,.2,.18],'confidence':1},'a'*64)
    assert not w.eligible({'status':'occluded','confidence':1},'a'*64)


def test_selected_art_is_full_canvas_and_cached(tmp_path,monkeypatch):
    image,s=fixture(tmp_path);monkeypatch.setattr(w,'ROOT',tmp_path/'cache')
    speaker={'speaker':'hero','status':'visible','confidence':1,'face_box':[.1,.1,.6,.8],'mouth_box':[.2,.3,.3,.4],'coverage_version':2,'mouth_geometry':{'evidence':'Visible complete lips'}}
    layers={}
    for pose in ('closed','half','open'):
        p=tmp_path/(pose+'.png');Image.new('RGBA',(40,20),'red').save(p);layers[pose]=str(p)
    def reused(image,speaker):speaker['layers']=layers;return True
    def upload(path,sha):
        with Image.open(path) as im:
            assert im.size==(400,200) and im.mode=='RGBA' and im.getchannel('A').getbbox()==(80,60,120,80)
        return {'sha256':sha,'gcs_bucket':'test','gcs_path':str(path),'media_url':'/api/std/assets/gcs-file?path='+sha}
    with patch('ae_mouth.locate_speakers',return_value=[speaker]) as locate,patch('worker.wuxia_mouth_preparation.eligible',return_value=True),patch('prepared_mouth_layers.prepare_scene',return_value={'entries':[speaker]}),patch('prepared_mouth_layers.reuse_prepared',side_effect=reused):
        first=w.prepare_art(s,'test',lambda ref,p:shutil.copyfile(image,p),upload,runner=Runner())
        second=w.prepare_art(s,'retry',lambda ref,p:shutil.copyfile(image,p),upload,runner=Runner())
        assert locate.call_count==1
        assert first==second
        assert first['report']['eligible_count']==1
        assert set(first['states'][0]['art'][0]['poses'])=={'closed','half','open'}


def test_final_recording_binding_and_stale_voice_rejection(tmp_path):
    image,s=fixture(tmp_path);audio_path=tmp_path/'audio';audio_path.write_bytes(b'recording')
    rows=[{'id':'r1','scene_number':1,'dialogue_kind':'dialogue','dialogue_speaker':'서진','text':'안녕.','voice_id':'v1','start_num':0.,'end_num':1.}]
    audio={'id':'audio1','metadata':{'sha256':digest(audio_path),'subtitle_timeline':[{'text':'안녕.','voice_id':'v1','start':0.,'end':1.}]}}
    art={'states':[{'scene_id':'E01_S01','asset_id':'STATE','sha256':digest(image),'art':[{'speaker':'hero','block_ids':['B1'],'automation':w.AUTOMATION}]}],'report':{'selection_complete':True}}
    with patch('ae_mouth.decode_scene_audio',return_value=[1000]*8000),patch('ae_media_utils.ffmpeg',return_value='ffmpeg'):
        bound=w.bind_timing(s,rows,audio,audio_path,art)
        mouth=bound['states'][0]['mouths'][0]
        assert mouth['audio_asset_id']=='audio1' and mouth['bindings'][0]['dialogue_speaker']=='서진'
        assert any(c['pose']=='open' for c in mouth['cues'])
        assert mouth['cues'][-1]['pose']=='closed'
        rows[0]['voice_id']='changed'
        with pytest.raises(ValueError,match='differs from saved'):
            w.bind_timing(s,rows,audio,audio_path,art)
    audio_path.write_bytes(b'changed')
    with pytest.raises(ValueError,match='checksum'):
        w.bind_timing(s,rows,audio,audio_path,art)


def test_workflow_owner_and_guidance():
    from worker.workflow_roles import asset_stage,PREPARATION
    from worker.script_worker_guidance import load_production_guidance
    assert asset_stage({'metadata':{'kind':'wuxia_mouth_preparation'}})==PREPARATION
    assert '앞으로의 자동 준비·확정 음성 연결' in load_production_guidance()

@pytest.mark.parametrize('failure',[False,True])
def test_durable_worker_zero_and_retry_are_distinct(tmp_path,monkeypatch,failure):
    import ae_highlight_worker as ae
    from worker.wuxia_mouth_worker import process_one
    image,structure=fixture(tmp_path)
    if not failure:structure['wuxia_ae_package']['scenes'][0]['graphics']=[]
    inp={'task':'art','source':{'package':structure['wuxia_ae_package'],'policy':{'auto_prepare':True},'cast':{'main':structure['main_character']}}}
    meta={'kind':'wuxia_mouth_preparation','state':'processing','input':inp,'attempts':0}
    job={'id':'job','project_id':'p','metadata':meta}
    saved=[];finished=[]
    class Response:
        def __init__(self,data):self.data=data
        def json(self):return self.data
    def request(method,url,headers,**kwargs):
        if url.endswith('/claim_std_wuxia_mouth'):
            meta['worker_token']=kwargs['json']['p_token'];return Response(job)
        if url.endswith('/finish_std_wuxia_mouth'):
            finished.append(kwargs['json']['p_result']);return Response({'applied':True})
        if url.endswith('/std_projects'):return Response([{'id':'p','status':'claimed','submitted_at':None}])
        if method=='PATCH':saved.append(kwargs['json']['metadata']);return Response([job])
        raise AssertionError(url)
    monkeypatch.setattr(ae,'_supabase',lambda:('https://example.invalid',{}))
    monkeypatch.setattr(ae,'_request',request)
    monkeypatch.setattr(ae,'_download_gcs_file',lambda ref,p:shutil.copyfile(image,p))
    monkeypatch.setattr(w,'ROOT',tmp_path/'cache')
    with patch('ae_mouth.locate_speakers',side_effect=RuntimeError('CLI unavailable')):
        assert process_one() is True
    if failure:
        assert not finished and saved[-1]['state']=='queued' and saved[-1]['attempts']==1
        assert 'CLI unavailable' in saved[-1]['error'] and saved[-1]['retry_after']
    else:
        assert finished[0]['report']['state']=='not_required' and not saved
