import copy
import hashlib
import json
import shutil
from pathlib import Path
from unittest.mock import patch
import pytest
from PIL import Image
from worker import wuxia_art_quality as q
from worker import wuxia_mouth_preparation as m


def review(sha, verdict='pass'):
    return {'source_sha256':sha,'coverage':{'all_people':True,'all_visible_hands':True},
        'people':[{'id':'hero','box':[.1,.1,.9,.9],'head_vs_torso':'head and shoulders share the same forward three-quarter direction'}],
        'hands':[{'owner_id':'hero','side':'left','box':[.3,.4,.5,.6],'chain_visibility':'occluded',
                  'chain_evidence':'four digits visible, thumb behind grip; elbow hidden by sleeve, not inferred'}],
        'checks':{k:{'verdict':verdict if k=='wrist_rotation' else 'pass',
                     'evidence':'Actual pixel observation of '+k,'boxes':[[.3,.4,.5,.6]]} for k in q.CHECKS}}


def fixture(tmp_path, monkeypatch):
    monkeypatch.setattr(q,'ROOT',tmp_path/'cache')
    image=tmp_path/'source.png';Image.new('RGB',(360,240),'tan').save(image)
    sha=hashlib.sha256(image.read_bytes()).hexdigest()
    state={'asset_id':'STATE','sha256':sha,'gcs_bucket':'test','gcs_path':'source.png'}
    scene={'scene_id':'E01_S01','states':[state],'graphics':[]}
    return image,state,scene


def test_new_only_policy_preserves_speech_and_explicit_anatomy_disable():
    p={'script':'UNCHANGED','audio_url':'saved','structure':{'image_style':'wuxia_webtoon'}}
    original=copy.deepcopy(p);q.enable_new_package(p)
    assert q.enabled(p['structure']) and p['script']==original['script'] and p['audio_url']=='saved'
    p['structure']['wuxia_mouth_policy']['anatomy_auto']['enabled']=False
    q.enable_new_package(p);assert not q.enabled(p['structure'])
    other={'structure':{'image_style':'watercolor'}};assert q.enable_new_package(other)==other


def test_occluded_fingers_not_forced_to_five_and_neck_failure_not_a_pass():
    sha='a'*64;r=review(sha)
    assert q.validate(r,sha)=='passed'
    r['checks']['head_neck']['verdict']='fail';r['passed']=True
    assert q.validate(r,sha)=='repair_required'
    r=review(sha);r['hands'][0]['side']='uncertain'
    assert q.validate(r,sha)=='uncertain'


def test_incomplete_invented_or_stale_review_is_rejected():
    sha='a'*64
    for mutate in [lambda r:r.update(source_sha256='b'*64),
                   lambda r:r['coverage'].update(all_visible_hands=False),
                   lambda r:r['hands'][0].update(owner_id='not-in-picture'),
                   lambda r:r['checks']['head_neck'].update(verdict='fail',boxes=[])]:
        r=review(sha);mutate(r)
        with pytest.raises(ValueError):q.validate(r,sha)


def test_actual_pixels_tiled_cached_and_failed_source_yields_repair_job(tmp_path,monkeypatch):
    image,state,scene=fixture(tmp_path,monkeypatch);calls=[]
    class Runner:
        def _stage(self,identity,name,context,task):
            paths=context['_local_image_paths'];assert len(paths)==7
            assert all(Path(p).is_file() for p in paths)
            assert Image.open(paths[1]).size==(165,144)
            assert 'four-finger' in task and 'head-to-neck' in task
            calls.append(name);return review(state['sha256'],'fail')
    source=image.read_bytes()
    a=q.review_state(state,scene,'x',lambda ref,p:shutil.copyfile(image,p),lambda:None,Runner())
    b=q.review_state(state,scene,'retry',lambda ref,p:pytest.fail('reuse verified source'),lambda:None,Runner())
    assert a==b and calls==['anatomy_actual_source']
    assert not a['passed'] and a['decision']=='repair_required'
    assert a['repair_request']['method']=='localized_edit'
    assert a['repair_request']['overwrite_source'] is False and not a['actual_repair_performed']
    assert image.read_bytes()==source
    assert Path(a['evidence_file']).is_file()


def test_checksum_and_tool_errors_do_not_become_zero_or_pass(tmp_path,monkeypatch):
    image,state,scene=fixture(tmp_path,monkeypatch)
    class Failed:
        def _stage(self,*args):raise RuntimeError('Codex CLI failed')
    with pytest.raises(RuntimeError,match='CLI failed'):
        q.review_state(state,scene,'x',lambda ref,p:shutil.copyfile(image,p),lambda:None,Failed())
    state['sha256']='b'*64
    with pytest.raises(ValueError,match='checksum'):
        q.review_state(state,scene,'x',lambda ref,p:shutil.copyfile(image,p),lambda:None,Failed())


def test_changed_repair_pixels_require_new_review_not_old_approval(tmp_path,monkeypatch):
    image,state,scene=fixture(tmp_path,monkeypatch);calls=[]
    class Runner:
        def _stage(self,identity,name,c,task):calls.append(c['source_sha256']);return review(c['source_sha256'])
    q.review_state(state,scene,'x',lambda ref,p:shutil.copyfile(image,p),lambda:None,Runner())
    Image.new('RGB',(360,240),'navy').save(image);state['sha256']=hashlib.sha256(image.read_bytes()).hexdigest()
    q.review_state(state,scene,'x',lambda ref,p:shutil.copyfile(image,p),lambda:None,Runner())
    assert len(calls)==2 and calls[0]!=calls[1]


def test_anatomy_precedes_all_optional_effects_and_rejected_state_is_not_animated(tmp_path,monkeypatch):
    image,state,scene=fixture(tmp_path,monkeypatch);good={**state,'asset_id':'GOOD'};scene['states'].append(good)
    structure={'wuxia_ae_package':{'scenes':[scene]},'wuxia_mouth_policy':{'enabled':False,'auto_prepare':False,
        'anatomy_auto':{'contract':q.CONTRACT,'enabled':True},'cinematic_auto':{'enabled':True,'auto_prepare':True},
        'energy_auto':{'enabled':True,'auto_prepare':True}}}
    order=[]
    def audit(*args):
        order.append('anatomy')
        return {'STATE':{'passed':False,'decision':'repair_required','repair_request':{'asset_id':'STATE'}},
                'GOOD':{'passed':True,'decision':'passed','repair_request':None}}
    def cinematic(sc,*args):order.append('cinematic');assert [s['asset_id'] for s in sc['states']]==['GOOD'];return {}
    def energy(st,*args):order.append('energy');assert st['asset_id']=='GOOD';return {'loops':[],'decision':'absent'}
    with patch.object(q,'audit_package',side_effect=audit),patch('worker.wuxia_cinematic.prepare_scene',side_effect=cinematic),patch('worker.wuxia_energy_preparation.prepare_state',side_effect=energy):
        result=m.prepare_art(structure,'x',None,None,runner=object())
    assert order==['anatomy','cinematic','energy']
    assert result['report']['anatomy_review_state']=='repair_required'
    assert result['report']['state']!='not_required'
    assert result['report']['anatomy_repair_requests']==[{'asset_id':'STATE'}]
    assert result['states'][0]['art']==[] and 'energy' not in result['states'][0]
