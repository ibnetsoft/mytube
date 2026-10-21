import copy
import json
import subprocess
import sys
from pathlib import Path
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'worker'))
from scene_direction_policy import CONTRACT, validate_execution, validate_keys, require_execution_match
from directed_graphics import DIRECTED_GRAPHICS_JSX
from scene_direction_policy import bind_recorded_direction, bind_recorded_bubbles, recording_fingerprint, bind_prepared_camera


def design():
    return {'camera': {'kind': 'push', 'reason': 'Read the clue', 'reversal_reason': '',
        'keys': [dict(t=0,x=.5,y=.5,scale=1,rotation=0,opacity=100), dict(t=1,x=.5,y=.5,scale=1.03,rotation=0,opacity=100)]},
        'cue': {'quote': 'the letter', 'phase': 'during'},
        'effects': [], 'transition': {'kind':'cut','reason':'Keep the quiet reveal continuous'},
        'graphics': {'speech_bubbles': False, 'speedlines': False, 'reason': 'Quiet revelation'}}


def test_rejects_old_sustained_return_path_but_allows_deliberate_action():
    keys = design()['camera']['keys']
    keys.insert(1, {**keys[-1], 't': .5, 'scale': 1.05})
    with pytest.raises(ValueError, match='reversal'): validate_keys(keys)
    validate_keys(keys, 'Follow the visible hand withdrawing from the letter')


def test_hold_stays_still_and_graphics_follow_topic_language():
    d = design()
    d['camera']['kind'] = 'hold'
    with pytest.raises(ValueError, match='Hold'): validate_execution(d, {'visual_language':'cinematic'}, {})
    d = design(); d['graphics']['speedlines'] = True
    with pytest.raises(ValueError, match='Speedlines'): validate_execution(d, {'visual_language':'cinematic'}, {'narration':'Read the letter'})
    validate_execution(d, {'visual_language':'comic_action'}, {'narration':'Read the letter'})


def test_final_voice_cannot_silently_change_quote_or_inject_speedlines():
    d = design()
    with pytest.raises(ValueError, match='unique exact'): validate_execution(d, {}, {'narration':'No letter here'})
    direction={'contract':CONTRACT,'execution_design':d}
    with pytest.raises(ValueError, match='not directed'): require_execution_match(direction,d['camera']['keys'],[{'type':'speedline_burst'}])
    require_execution_match({'contract':'scene_direction_plan/v1'},[])  # archived plans are untouched


def test_unified_bubble_is_one_non_self_intersecting_closed_outline(tmp_path):
    source = 'function Shape(){}\n' + DIRECTED_GRAPHICS_JSX + '\nconsole.log(JSON.stringify(["left","right","none"].map(function(t){return directedBubbleOutline(500,160,t)})));'
    script=tmp_path/'geometry.cjs';script.write_text(source)
    shapes=json.loads(subprocess.check_output(['node',str(script)],text=True))
    def cross(a,b,c): return (b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0])
    for shape in shapes:
        vertices=shape['vertices']; n=len(vertices)
        assert shape['closed'] and len(shape['inTangents']) == len(shape['outTangents']) == n
        for i in range(n):
            for j in range(i+2,n):
                if i==0 and j==n-1: continue
                a,b,c,d=vertices[i],vertices[(i+1)%n],vertices[j],vertices[(j+1)%n]
                assert not (cross(a,b,c)*cross(a,b,d)<0 and cross(c,d,a)*cross(c,d,b)<0)
    assert len(shapes[0]['vertices'])==len(shapes[2]['vertices'])+3


def test_directed_hold_does_not_select_keyword_impact_or_ambient_effects():
    import codex_content_runner as planner
    d=design();d['camera']['kind']='hold';d['camera']['keys'][1]['scale']=1
    scene={'scene_number':1,'duration_seconds':5,'narration':'강타 폭발 the letter',
        'scene_direction_plan': {'contract':CONTRACT,'execution_design':d,'ae_operations':['hold'],
            'primary_effect':'hold','visual_strategy':'Hold the reaction','effect_limits':{}}}
    planner._plan_ae_effects_for_scenes([scene],{})
    planner._plan_ae_motion_for_scenes([scene],{})
    assert not scene['ae_effect_plan']['enabled']
    assert scene['ae_motion_plan']['vfx']==[]
    assert not any(scene['ae_motion_plan']['motion'].values())


def test_recorded_cues_bind_camera_and_bubbles_without_mutating_saved_intent():
    d=design(); direction={'contract':CONTRACT,'execution_design':d}
    payload={'subtitle_source_audio_id':'voice', 'subtitles':[
        {'scene_number':1,'text':'Read ','start':10,'end':12},
        {'scene_number':1,'text':'the letter','start':12,'end':16},
        {'scene_number':1,'text':' quietly','start':16,'end':20}]}
    before=copy.deepcopy(direction)
    bound,binding=bind_recorded_direction(direction,payload,1)
    assert [k['t'] for k in bound['execution_design']['camera']['keys']]==[0,.2,.6,1]
    assert direction==before
    spec={'enabled':True,'bubbles':[{'text':'the letter','start_seconds':0,'end_seconds':99}]}
    assert bind_recorded_bubbles(spec,payload,1,binding)['bubbles'][0]['start_seconds']==2
    assert spec['bubbles'][0]['start_seconds']==0
    changed=copy.deepcopy(payload);changed['subtitles'][1]['end']=17
    assert recording_fingerprint(changed,1)!=binding['fingerprint']
    # Translation-only metadata does not change the recorded acting/timing contract.
    changed=copy.deepcopy(payload);changed['subtitles'][1]['ko_text']='편지'
    assert recording_fingerprint(changed,1)==binding['fingerprint']
    again,_=bind_recorded_direction(bound,payload,1)
    assert again['execution_design']['camera']['keys']==bound['execution_design']['camera']['keys']


def test_reviewed_psd_uses_bound_camera_on_a_copy_and_legacy_is_unchanged():
    from test_ae_scene_preparation import plan
    direction={'contract':CONTRACT,'execution_design':design()}
    prepared={'plan':{**plan(),'direction_policy':direction}}
    before=copy.deepcopy(prepared)
    keys=design()['camera']['keys']
    result=bind_prepared_camera(prepared,{'creative_reference':direction},{'keys':keys,'effects':[]})
    assert prepared==before and result['plan']['camera'][-1]['scale']==1.03
    assert result['plan']['transition']=={'in':'cut','out':'cut','fraction':0}
    assert result['plan']['effects']==[]
    with pytest.raises(ValueError,match='transition'):
        require_execution_match(direction,keys,[], 'fade')
    assert bind_prepared_camera(prepared,{'creative_reference':{'contract':'scene_direction_plan/v1'}},{}) is prepared


def test_effect_selection_is_limited_grounded_and_requires_event_cue_when_transient():
    d=design();d['effects']=[{'type':'light_sweep','reason':'A narrow reflection crosses the visible letter foil.',
        'intensity':.24,'center':[.61,.48],'radius':.18,'color':[1,.8,.45],
        'event':{'quote':'the letter','phase':'during','at':'middle','duration_seconds':.4}}]
    topic={'genre':'quiet family mystery','visual_language':'illustrated_drama','reason':'A letter changes the family story.',
        'continuity_rules':['Keep the envelope on the table.']}
    scene={'duration_seconds':6,'narration':'She found the letter beside the window.'}
    plan=validate_execution(d,topic,scene)
    assert plan['effects'][0]['type']=='light_sweep'
    d['effects']=[{**d['effects'][0],'intensity':.8}]
    with pytest.raises(ValueError,match='restrained'):validate_execution(d,topic,scene)
    d=design();d['effects']=[{'type':'impact_shake','reason':'A sudden object strike is visible.',
        'intensity':.25,'center':[.5,.5],'radius':.2,'color':[1,1,1],
        'event':{'quote':'the letter','phase':'during','at':'start','duration_seconds':.2}}]
    d['camera']['keys'][1]['scale']=1.02
    with pytest.raises(ValueError,match='overscan'):validate_execution(d,topic,scene)


def test_reviewed_psd_receives_only_the_bound_effects_and_final_sequence_transition():
    from test_ae_scene_preparation import plan
    d=design();d['effects']=[{'type':'light_sweep','reason':'A reflection crosses the visible seal.',
        'intensity':.2,'center':[.55,.58],'radius':.16,'color':[1,.8,.45]}]
    d['transition']={'kind':'crossfade','duration_seconds':.24,'reason':'Move from the letter detail to the quiet reaction.'}
    direction={'contract':CONTRACT,'execution_design':d}
    prepared={'plan':{**plan(),'direction_policy':direction}}
    before=copy.deepcopy(prepared)
    effects=[{'type':'light_sweep','start':.3,'end':.42,'intensity':.2,'center':[.55,.58],
              'radius':.16,'color':[1,.8,.45],'reason':'A reflection crosses the visible seal.'}]
    execution={'keys':d['camera']['keys'],'effects':effects,'transition':'crossfade'}
    result=bind_prepared_camera(prepared,{'creative_reference':direction},execution)
    assert result['plan']['effects']==effects
    assert result['plan']['transition']=={'in':'cut','out':'cut','fraction':0}
    assert prepared==before
