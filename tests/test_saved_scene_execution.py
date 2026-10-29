import copy,sys
from pathlib import Path
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'worker'))
from saved_scene_execution import bind_prepared,validate_lights,CONTRACT
from uploaded_video_passthrough import eligible

def direction():
    return {'keys':[{'t':0,'x':.5,'y':.5,'scale':1,'rotation':0,'opacity':100},{'t':1,'x':.5,'y':.5,'scale':1,'rotation':0,'opacity':100}], 'effects':[],'lights':[]}
def test_prepared_depth_planes_execute_distinct_movement_without_flat_fake_layers():
    prepared={'plan':{'layers':[{'id':r,'role':r} for r in ('background','character','foreground')]},'layers':{}}
    execution=direction();execution['layer_motion']={'contract':CONTRACT,'from':.1,'to':.3,'move_x':-.012}
    scene={'saved_direction_binding':{'contract':CONTRACT}}
    result=bind_prepared(prepared,scene,execution)
    motion={l['role']:l['motion'][-1]['x'] for l in result['plan']['layers']}
    assert motion=={'background':0,'character':-.006,'foreground':-.012}
    assert 'motion' not in prepared['plan']['layers'][0]
def test_missing_real_layer_is_rejected():
    execution=direction();execution['layer_motion']={'contract':CONTRACT,'from':.1,'to':.3,'move_x':-.012}
    with pytest.raises(ValueError,match='Actual background'):
        bind_prepared({'plan':{'layers':[{'id':'original','role':'background'}]}},{'saved_direction_binding':{'contract':CONTRACT}},execution)
def test_light_only_scene_cannot_be_mistaken_for_no_effect_passthrough():
    execution=direction();execution['lights']=[{'color':[1,.9,.75],'center':[.5,.5],'radius':.25,'keys':[{'t':0,'opacity':0},{'t':.5,'opacity':6},{'t':1,'opacity':0}]}]
    assert validate_lights(execution['lights'])==execution['lights']
    assert not eligible({'source_kind':'image'},{'scene':execution},runtime_resolved=True)
def test_unsafe_light_opacity_is_rejected():
    with pytest.raises(ValueError):validate_lights([{'color':[1,1,1],'center':[.5,.5],'radius':.25,'keys':[{'t':0,'opacity':0},{'t':1,'opacity':99}]}])
