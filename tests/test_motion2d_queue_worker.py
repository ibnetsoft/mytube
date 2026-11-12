import copy
import shutil
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'worker'))
from motion2d_queue_worker import check_current
import motion2d_queue_worker
import motion2d_mvp
from test_motion2d_saved_assets import setup
from worker.workflow_roles import PREPARATION, POSTPRODUCTION, asset_stage


def make_context(tmp_path):
    snapshot=setup(tmp_path)
    snapshot['scene_identity']=[{'id':'scene','scene_number':1}]
    row={'text':'안녕하세요','start':0,'end':4,'voice_id':'voice'}
    snapshot['audio']['metadata']['subtitle_timeline']=[row]
    project={'id':'p','status':'in_progress','submitted_at':None,'progress_payload':{'tts_asset_id':'audio'},'project_payload':{'script':'안녕하세요','subtitles':[row],'subtitle_source_audio_id':'audio'}}
    assets=copy.deepcopy([snapshot['image'],snapshot['audio'],snapshot['background'],*snapshot['patches'].values()])
    class Fake:
        def _request(self, method, url, headers, params):
            if url.endswith('std_projects'):return SimpleNamespace(json=lambda:[project])
            if url.endswith('std_project_scenes'):return SimpleNamespace(json=lambda:[{'id':'scene','scene_number':1}])
            if 'id' in params:return SimpleNamespace(json=lambda:copy.deepcopy(assets))
            if params.get('asset_type')=='eq.image':return SimpleNamespace(json=lambda:[{'id':snapshot['image']['id']}])
            role=params['metadata->>role'][3:]
            return SimpleNamespace(json=lambda:[{'id':snapshot['patches'][role]['id']}])
    return snapshot,project,assets,Fake()


def test_scene_patch_job_belongs_to_preparation():
    assert asset_stage({'metadata':{'kind':'motion2d_render'}})==PREPARATION
    assert asset_stage({'metadata':{'kind':'motion2d_render'}})!=POSTPRODUCTION


def test_current_input_validation_and_changes(tmp_path):
    snapshot,project,assets,ae=make_context(tmp_path)
    check_current(ae,'https://db',{}, {'project_id':'p'},snapshot)
    project['submitted_at']='now'
    with pytest.raises(ValueError):check_current(ae,'https://db',{}, {'project_id':'p'},snapshot)
    project['submitted_at']=None
    project['progress_payload']['tts_asset_id']='different'
    with pytest.raises(ValueError, match='음성'):check_current(ae,'https://db',{}, {'project_id':'p'},snapshot)
    project['progress_payload']['tts_asset_id']='audio'
    assets[-1]['metadata']['sha256']='0'*64
    with pytest.raises(ValueError, match='변경'):check_current(ae,'https://db',{}, {'project_id':'p'},snapshot)


def test_queued_job_downloads_registered_patches_and_publishes_verified_video(tmp_path,monkeypatch):
    snapshot,project,assets,reader=make_context(tmp_path)
    job={'id':'job','project_id':'p','updated_at':'v1','metadata':{'kind':'motion2d_render','state':'queued','input':snapshot},'workflow_project':{'id':'p','status':'in_progress','submitted_at':None}}
    uploads=[]
    class Fake:
        GcsRef=staticmethod(lambda bucket,key:(bucket,key))
        _supabase=staticmethod(lambda:('https://db',{}))
        _now=staticmethod(lambda:'2026-11-12T00:00:00Z')
        _download_gcs_file=staticmethod(lambda ref,target:shutil.copyfile(ref[1],target))
        @staticmethod
        def _upload_gcs_file(path,key,mime):
            assert path.is_file() and mime=='video/mp4';uploads.append(path.read_bytes());return ('b',key,'url')
        @staticmethod
        def _request(method,url,headers,params=None,json=None):
            if method=='PATCH':
                job['metadata']=copy.deepcopy(json['metadata']);return SimpleNamespace(json=lambda:[copy.deepcopy(job)])
            if 'workflow_project.submitted_at' in params:return SimpleNamespace(json=lambda:[copy.deepcopy(job)])
            return reader._request(method,url,headers,params)
    import worker_config
    monkeypatch.setattr(worker_config,'TEMP_DIR',tmp_path/'temp')
    binary=tmp_path/'rhubarb.exe';binary.write_bytes(b'test')
    monkeypatch.setenv('AIR_MOTION2D_RHUBARB',str(binary))
    monkeypatch.setattr(motion2d_mvp,'rhubarb_cues',lambda *a:[{'start':0,'end':1,'pose':'half'}])
    monkeypatch.setitem(sys.modules,'ae_highlight_worker',Fake())
    monkeypatch.setitem(sys.modules,'ae_scene_preparation',SimpleNamespace(claimable_filter=lambda:'filter'))
    assert motion2d_queue_worker.process_one()
    assert job['metadata']['state']=='ready'
    assert job['metadata']['result']['frames']==96
    assert job['metadata']['result']['patch_assets']['hair']=='hair'
    assert len(uploads)==1 and len(uploads[0])>1000
