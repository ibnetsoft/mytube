import copy,sys
from pathlib import Path
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'worker'))
import purpose_direction as p
from test_scene_direction_policy import design

def fixture():
    d=design();d['camera']['keys'][1].update(x=.506,scale=1.012)
    policy=p.policy({'has_character_dialogue':True},'action')
    creative={'contract':'scene_direction_plan/v2','purpose_policy':policy,'execution_design':d}
    scene={'number':1,'start':4.,'end':8.,'text':'Please stay.', 'source':{'id':'immutable'},'purpose_policy':policy,'creative_reference':creative,'prepared_direction':{'source':'psd','keys':copy.deepcopy(d['camera']['keys']),'effects':[{'type':'focus_glow'}],'transition':'crossfade'},'reviewed_depth_effects':[{'type':'depth_background_blur','intensity':.12}]}
    return scene

def test_actual_dialogue_has_priority_and_restrains_camera_effects():
    scene=fixture();policy=scene['purpose_policy'];assert policy['role']=='dialogue'
    p.validate_design(policy,scene['prepared_direction']['keys'],[])
    with pytest.raises(ValueError,match='unsuitable'):p.validate_design(policy,scene['prepared_direction']['keys'],[{'type':'impact_flash','intensity':.1}])
    keys=copy.deepcopy(scene['prepared_direction']['keys']);keys[-1]['x']=.52
    with pytest.raises(ValueError,match='max_move'):p.validate_design(policy,keys,[])
    p.validate_design(p.policy({},'location'),keys,[])

def test_repair_reduces_only_added_direction_and_is_idempotent_and_bounded():
    scene=fixture();original=copy.deepcopy(scene)
    r=p.repair(scene,1,'Actual output distracts from the speaker')
    assert r['factor']==.5 and scene['prepared_direction']['effects']==[]
    assert scene['prepared_direction']['keys'][-1]['x']==pytest.approx(.503)
    assert scene['reviewed_depth_effects'][0]['intensity']==.06
    assert (scene['start'],scene['end'],scene['text'],scene['source'])==(4.,8.,original['text'],original['source'])
    once=copy.deepcopy(scene['prepared_direction']);p.repair(scene,1,'same failure on resume');assert scene['prepared_direction']==once
    p.repair(scene,2,'Still too strong');assert scene['prepared_direction']['keys'][-1]['x']==pytest.approx(.5015)
    assert scene['reviewed_depth_effects'][0]['intensity']==.05
    with pytest.raises(ValueError):p.repair(scene,3,'Never loop indefinitely')

def test_bad_art_or_audio_can_never_be_auto_approved_or_retimed():
    response={'repair_scope':'direction_only','checks':[{'id':'purpose_fit','passed':False,'evidence':'Actual camera sweeps across the speaker.'}]}
    assert p.repairable_review(response)
    for unsafe in ('source_identity','narration_integrity','artifacts','captions'):
        failed={'id':unsafe,'passed':False,'evidence':'Actual source/output defect'}
        assert not p.repairable_review({**response,'checks':[failed]})
    assert not p.repairable_review({**response,'checks':[]})
    assert not p.repairable_review({**response,'repair_scope':'uncertain'})

def test_script_validation_repairs_twice_using_unchanged_script_and_feedback():
    calls=[];context={'script':'immutable narration','dialogue':['speaker: exact line']}
    def stage(job,name,ctx,task):
        assert ctx['script']==context['script'] and ctx['dialogue']==context['dialogue']
        calls.append(name)
        if len(calls)>1:assert 'purpose intensity' in ctx['validation_feedback']['error']
        return {'ready':len(calls)==3}
    def validate(result):
        if not result['ready']:raise ValueError('purpose intensity excessive')
        return 'reviewed script direction'
    assert p.direct_with_repair(stage,'job',context,'direction only',validate)=='reviewed script direction'
    assert calls==['02f_scene_visual_director','02f_scene_visual_director_repair_1','02f_scene_visual_director_repair_2']
    assert 'validation_feedback' not in context

def test_native_layer_motion_also_obeys_dialogue_limits():
    from test_ae_scene_preparation import plan
    scene=fixture();native=plan();native['layers'][1]['motion']=[dict(t=t,x=t*.03,y=0,scale=1,rotation=0,opacity=100) for t in (0,1)]
    with pytest.raises(ValueError,match='max_move'):p.validate_native(scene,native)


def test_repair_rebinds_camera_and_depth_once_without_touching_approved_package():
    from test_ae_scene_preparation import plan
    from scene_direction_policy import bind_prepared_camera
    from depth_finishing import assert_applied
    scene=fixture();approved={'plan':{**plan(),'direction_policy':copy.deepcopy(scene['creative_reference']),'effects':copy.deepcopy(scene['reviewed_depth_effects'])}}
    approved['plan']['effects'][0].update(target_layer='background',blur_pixels=6,start=0,end=1,center=[.5,.5],radius=.5,color=[.8,.8,.9],reason='Distant garden')
    scene['reviewed_depth_effects']=copy.deepcopy(approved['plan']['effects']);before=copy.deepcopy(approved)
    p.repair(scene,1,'Background is too strong beside quiet dialogue')
    execution=scene['prepared_direction'];runtime=bind_prepared_camera(approved,scene,execution);runtime=p.apply_native_repair(scene,runtime)
    assert runtime['plan']['camera'][-1]['x']==pytest.approx(.503)
    assert runtime['plan']['effects'][0]['intensity']==.06
    assert_applied(scene['reviewed_depth_effects'],runtime['plan']);p.validate_native(scene,runtime['plan'])
    assert approved==before
    resumed=fixture();resumed['reviewed_depth_effects']=copy.deepcopy(before['plan']['effects']);p.repair(resumed,1,'Resume same repair')
    assert resumed['prepared_direction']==scene['prepared_direction']


def test_uploaded_video_repair_retains_dialogue_and_mandatory_effect_but_quiets_boundary():
    scene=fixture();scene['postwork']={'source_video_id':'source','dialogue':[{'text':'Exact line','speaker':'hero','start':4.,'end':5.}], 'requested_effects':[{'type':'fireflies','intensity':.12}], 'transition':{'kind':'fade_black'}}
    before=copy.deepcopy(scene['postwork']['dialogue']);p.repair(scene,1,'The finishing distracts from dialogue')
    assert scene['postwork']['dialogue']==before and scene['postwork']['source_video_id']=='source'
    assert scene['postwork']['requested_effects']==[{'type':'fireflies','intensity':.06}]
    assert scene['postwork']['transition']['kind']=='cut'


def test_final_review_retry_refreshes_stale_plan_and_resumes_applied_plan():
    receipt={'contract':p.CONTRACT,'attempt':1,'reason':'Actual boundary camera is excessive','factor':.5}
    scene=fixture();plan={'purpose_repair':receipt,'scene':copy.deepcopy(scene['prepared_direction'])}
    restored,refresh=p.restore_attempt(scene,plan)
    assert restored==receipt and refresh is True
    assert scene['prepared_direction']['keys'][-1]['x']==pytest.approx(.503)
    plan['purpose_repair_applied']=1
    resumed=fixture();_,refresh=p.restore_attempt(resumed,plan)
    assert refresh is False and resumed['prepared_direction']==scene['prepared_direction']
    plan['purpose_repair']={**receipt,'attempt':2}
    _,refresh=p.restore_attempt(fixture(),plan);assert refresh is True
