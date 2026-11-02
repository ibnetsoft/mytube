import copy, sys
from pathlib import Path
import pytest
from PIL import Image,ImageDraw
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'worker'))
from character_states import prepare_character_states, prepare_scene_states, assign_character_state_requests
from ae_scene_animation import write_scene_jsx

def test_scene_range_is_inclusive_and_includes_scenery_without_people():
    scenes = [{'scene_number': i, 'scene_text': str(i), 'scene_direction_plan': {'contract': 'test'}} for i in range(1, 8)]
    identity = {'scene_cast': [{'scene_number': i, 'characters': ['person'] if i != 4 else []} for i in range(1, 8)]}
    assign_character_state_requests(scenes, identity, {
        'character_state_count': 3, 'character_state_scene_start': 2, 'character_state_scene_end': 6}, 2)
    selected = [s['scene_number'] for s in scenes if s['scene_direction_plan'].get('scene_state_request')]
    assert selected == [3, 4, 5, 6]
    assert scenes[5]['scene_direction_plan']['scene_state_request'] == {'count': 3, 'scene_text': '6'}

def test_old_jobs_without_scene_range_are_unchanged():
    scenes = [{'scene_number': 20, 'scene_direction_plan': {'contract': 'test'}}]
    original = copy.deepcopy(scenes)
    assign_character_state_requests(scenes, {'scene_cast': [{'scene_number': 20, 'characters': ['person']}]}, {'character_state_count': 2}, 18)
    assert scenes == original

def test_generated_states_reach_actual_ae_writer(tmp_path):
    source=tmp_path/'character.png';Image.new('RGBA',(128,128),(0,0,0,0)).save(source)
    plan={'contract':'ae_scene/v1','schema_version':'ae_scene/v1','timing':'normalized','width':128,'height':128,
    'camera':[dict(t=t,x=.5,y=.5,scale=1,rotation=0) for t in (0,1)],
    'layers':[dict(id='bg',role='background',z_index=0),dict(id='person',role='character',z_index=1)],
    'lights':[],'transition':{'in':'cut','out':'cut','fraction':0},
    'continuity':dict(entry='same room',exit='same room',screen_direction='left',light_direction='left')}
    class Runner:
        def _stage(self,*args):return {'states':[{'start':.3,'change':'Look left'},{'start':.65,'change':'Raise eyebrows'}]}
    class Generator:
        def generate(self,**kwargs):
            assert kwargs['reference']==source and kwargs['role']=='character'
            kwargs['work_dir'].mkdir(parents=True)
            target=kwargs['work_dir']/'state.png';im=Image.new('RGBA',(128,128));ImageDraw.Draw(im).ellipse((40,20,80,100),fill='orange');im.save(target);return target
    original=copy.deepcopy(plan)
    updated,files,images=prepare_character_states(plan,[{'role':'layer','layer_id':'person','path':source}],{'count':3,'scene_text':'He looks left and reacts.'},Runner(),Generator(),tmp_path)
    assert original==plan and updated['layers'][0]==original['layers'][0]
    assert len(images)==2 and len(files)==3
    paths={f['layer_id']:f['path'] for f in files};paths['bg']=source
    target=tmp_path/'scene.jsx';write_scene_jsx(updated,paths,tmp_path/'scene.aep',tmp_path/'native.avi',target,3)
    script=target.read_text();assert 'person_state2' in script and 'ADBE Opacity' in script

def test_disabled_states_are_a_noop():
    p={'layers':[]};f=[]
    assert prepare_character_states(p,f,None,None,None,None)==(p,f,[])
