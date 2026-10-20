import sys
from pathlib import Path
import pytest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from worker.workflow_roles import PREPARATION, POSTPRODUCTION, belongs, asset_query, assert_project

@pytest.mark.parametrize('kind,task,owner',[
    ('ae_scene_preparation',None,PREPARATION),('ae_speaker_coordinates',None,PREPARATION),
    ('region_layer_package',None,PREPARATION),('motion_preview','direction',PREPARATION),
    ('motion_preview','preview',POSTPRODUCTION),('ae_mouth_job',None,POSTPRODUCTION),
    ('motion_automation',None,POSTPRODUCTION),('region_motion_plan',None,POSTPRODUCTION)])
def test_submission_flips_ownership_without_cross_claims(kind,task,owner):
    row={'metadata':{'kind':kind,'input':{'task':task}},'workflow_project':{'status':'in_progress','submitted_at':None}}
    assert belongs(row,PREPARATION)==(owner==PREPARATION)
    assert not belongs(row,POSTPRODUCTION)
    row['workflow_project']['submitted_at']='2026-10-20T00:00:00Z'
    assert not belongs(row,PREPARATION)
    assert belongs(row,POSTPRODUCTION)==(owner==POSTPRODUCTION)

def test_retired_preview_and_closed_projects_never_claimed():
    row={'metadata':{'kind':'ae_mouth_job','preview_sync':True},'workflow_project':{'status':'submitted','submitted_at':'yes'}}
    assert not belongs(row,POSTPRODUCTION)
    for status in ('completed','approved','canceled','cancelled','paid'):
        with pytest.raises(ValueError):assert_project({'status':status,'submitted_at':'yes'},POSTPRODUCTION)
    params=asset_query(POSTPRODUCTION,{'metadata->>kind':'eq.ae_mouth_job'})
    assert params['workflow_project.submitted_at']=='not.is.null'
    assert 'preview_sync' in params['and']

def test_image_preparation_receipt_cannot_start_ae(tmp_path):
    from worker.prepared_mouth_preview import prepare_preview
    result=prepare_preview('fixture',1,tmp_path/'source.png',{}, {'state':'ready','keys':['saved']})
    assert result['state']=='prepared' and result['voice_synced'] is False
    assert result['execution_owner']=='postproduction'

def test_script_console_retired_ae_endpoint_and_role_forwarding(monkeypatch):
    from fastapi.testclient import TestClient
    from worker import codex_local_console as console, local_production_settings as bridge
    captured=[]
    monkeypatch.setattr(bridge,'invoke',lambda *args:captured.append(args) or {'status':200,'data':{'projects':[]}})
    client=TestClient(console.app,base_url=console.ORIGIN,headers={'X-Codex-Local':console.TOKEN})
    assert client.post('/api/ae-highlight/start').status_code==410
    assert client.get('/api/local/projects').status_code==200
    assert captured[0][-1]==PREPARATION
    assert client.get('/api/local/projects',headers={'X-Codex-Local':'wrong'}).status_code==401
