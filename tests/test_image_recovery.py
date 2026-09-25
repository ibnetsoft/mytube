import json
import pathlib
import sys
import pytest
from PIL import Image

sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]/'worker'))
import image_recovery as r
import cowork_scene_assets as helper

def manifest():
    return {'schema':'cowork_scene_assets/v1','topic_id':'123','scene_count':4,
        'scene_specs':[{'scene_number':n,'image_prompt':f'Adult character holding document {n}'} for n in range(1,5)],
        'character_references':[{'name':'A','local_file':'reference.png'}],
        'grids':[{'grid_number':1,'scene_numbers':[1,2,3,4],'prompt':'A four-panel grid','raw_file':'grid-001.png'}]}

def event(s,action,job_id='grid-001',**kwargs):return r.transition(s,{'action':action,'job_id':job_id,**kwargs},now=1000)

def failed(kind):
    s=event(r.initialize(manifest()),'start')
    return event(s,'result',outcome=kind)

@pytest.mark.parametrize('kind',['safety','unknown','quota','unavailable'])
def test_refusal_and_unknown_never_auto_retry(kind):
    s=failed(kind)
    assert r.summary(s,10000)['runnable']==[]
    with pytest.raises(ValueError):event(s,'start')
    with pytest.raises(ValueError):event(s,'split_quality')

def test_safety_overrides_transient_label():
    s=event(r.initialize(manifest()),'start')
    s=event(s,'result',outcome='transient',code='content_filter')
    assert s['jobs'][0]['status']=='safety_review'

def test_transient_backoff_and_budget():
    s=failed('transient')
    with pytest.raises(ValueError):event(s,'start')
    for t in (1030,1150):
        s=r.transition(s,{'action':'start','job_id':'grid-001'},now=t)
        s=r.transition(s,{'action':'result','job_id':'grid-001','outcome':'transient'},now=t)
    assert s['jobs'][0]['status']=='exhausted'

def test_running_job_not_retried_after_restart(tmp_path):
    p=tmp_path/'manifest.json';p.write_text(json.dumps(manifest()))
    s=r.ensure_state(p)
    r.update_file(r.state_path(p),lambda s:event(s,'start'))
    assert not r.summary(r.ensure_state(p))['runnable']

def test_refused_alternative_needs_review_and_approval():
    s=failed('safety')
    review={'reviewer':'human','reason':'Different safe depiction','source_fidelity':'same event',
        'character_age_style_preserved':True}
    proposals=[{'scene_numbers':[n],'prompt':f'Still life of story document {n}'} for n in range(1,5)]
    with pytest.raises(ValueError):event(s,'review',decision='alternative',review=review,proposals=proposals)
    review.update(safety_assessment='allowed_alternative',user_approval='Explicit user approved alternative storyboard')
    s=event(s,'review',decision='alternative',review=review,proposals=proposals)
    assert len(r.summary(s,1000)['runnable'])==4
    assert all(j['references']==s['jobs'][0]['references'] for j in s['jobs'][1:])
    with pytest.raises(ValueError):event(s,'start')

def test_exact_mapping_required():
    s=failed('quality')
    with pytest.raises(ValueError):event(s,'review',decision='alternative',review={},proposals=[])

def test_quality_split_crop_resume_and_tamper_guard(tmp_path,monkeypatch):
    m=manifest();p=tmp_path/'manifest.json';p.write_text(json.dumps(m))
    s=event(failed('quality'),'split_quality')
    for job in s['jobs'][1:]:
        img=tmp_path/(job['id']+'.png');Image.new('RGB',(640,360),(50*job['scene_numbers'][0],10,20)).save(img)
        s=event(s,'start',job['id'])
        s=event(s,'result',job['id'],outcome='generated',image_file=str(img))
        assert not r.summary(s)['complete']
        s=event(s,'accept',job['id'],visual_review='Subject, continuity, scene and anatomy checked')
    r.state_path(p).write_text(json.dumps(s))
    assert r.summary(s)['complete']
    out=tmp_path/'cropped'
    assert len(helper.crop_grids(p,tmp_path,out,target_width=640,target_height=360))==4
    assert helper.crop_grids(p,tmp_path,out,target_width=640,target_height=360)==[]
    Image.new('RGB',(640,360),'black').save(out/'scene-001.png')
    with pytest.raises(FileExistsError):helper.crop_grids(p,tmp_path,out,target_width=640,target_height=360)
    monkeypatch.setattr(helper,'_topic',lambda *a:pytest.fail('No DB calls permitted before verification'))
    with pytest.raises(ValueError,match='Crop changed'):helper.publish(p,out,False)

def test_partial_state_cannot_publish(tmp_path,monkeypatch):
    p=tmp_path/'manifest.json';p.write_text(json.dumps(manifest()));r.ensure_state(p)
    monkeypatch.setattr(helper,'_topic',lambda *a:pytest.fail('No network call'))
    with pytest.raises(ValueError,match='Incomplete'):helper.publish(p,tmp_path,False)

def test_manifest_change_and_raw_tamper(tmp_path):
    p=tmp_path/'manifest.json';p.write_text(json.dumps(manifest()));r.ensure_state(p)
    m=manifest();m['topic_id']='456';p.write_text(json.dumps(m))
    with pytest.raises(ValueError,match='new manifest'):r.ensure_state(p)
    img=tmp_path/'raw.png';Image.new('RGB',(640,360),'red').save(img)
    s=event(r.initialize(manifest()),'start');s=event(s,'result',outcome='generated',image_file=str(img))
    Image.new('RGB',(640,360),'blue').save(img)
    with pytest.raises(ValueError,match='changed'):event(s,'accept',visual_review='checked')

def test_character_refusal_is_durable(monkeypatch,tmp_path):
    from codex_character_assets import NativeCodexImageGenerator
    generator=NativeCodexImageGenerator(None,tmp_path)
    calls=[]
    def refused(prompt):
        calls.append(prompt);raise RuntimeError('safety refusal')
    monkeypatch.setattr(generator,'_generate_once',refused)
    with pytest.raises(RuntimeError):generator.generate('adult portrait')
    with pytest.raises(ValueError,match='not runnable'):generator.generate('adult portrait')
    assert len(calls)==1

def test_thumbnail_and_character_supported():
    assert r.initialize({'schema':'cowork_thumbnail_asset/v1','prompt':'text-free landscape'})['jobs'][0]['kind']=='thumbnail'
    assert r.initialize({'jobs':[{'id':'hero','kind':'character','layout':'single','scene_numbers':[], 'prompt':'portrait'}]})['jobs'][0]['kind']=='character'

def test_character_ready_result_reused(monkeypatch,tmp_path):
    from codex_character_assets import NativeCodexImageGenerator
    generator=NativeCodexImageGenerator(None,tmp_path)
    img=tmp_path/'portrait.png';Image.new('RGB',(512,512),'red').save(img)
    calls=[]
    monkeypatch.setattr(generator,'_generate_once',lambda prompt:(calls.append(prompt) or img))
    assert generator.generate('adult portrait')==img
    assert generator.generate('adult portrait')==img
    assert len(calls)==1

def test_thumbnail_publish_gate_before_network(monkeypatch,tmp_path):
    import cowork_thumbnail_asset as thumb
    m={'schema':'cowork_thumbnail_asset/v1','topic_id':'123','prompt':'text-free landscape'}
    p=tmp_path/'thumbnail.json';p.write_text(json.dumps(m));r.ensure_state(p)
    monkeypatch.setattr(thumb,'_topic',lambda *a:pytest.fail('No network before ready'))
    with pytest.raises(ValueError,match='incomplete'):
        thumb.publish('123',tmp_path/'missing.png',manifest_path=p)

def test_single_alternative_cannot_branch_forever():
    s=event(failed('quality'),'split_quality')
    s=event(s,'start','grid-001-alt-1')
    s=event(s,'result','grid-001-alt-1',outcome='quality')
    with pytest.raises(ValueError,match='budget'):
        event(s,'review','grid-001-alt-1',decision='alternative',review={},proposals=[])

def test_locked_state_not_overwritten(tmp_path):
    p=tmp_path/'manifest.json';p.write_text(json.dumps(manifest()));r.ensure_state(p)
    state=r.state_path(p);lock=state.with_suffix(state.suffix+'.lock');lock.touch()
    with pytest.raises(FileExistsError):r.update_file(state,lambda s:event(s,'start'))
    assert json.loads(state.read_text())['jobs'][0]['status']=='pending'
