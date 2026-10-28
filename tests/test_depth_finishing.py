import sys,copy
from pathlib import Path
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'worker'))
from depth_finishing import normalize
from ae_scene_effects import validate_effects
from test_ae_scene_preparation import plan

def depth(kind='depth_background_blur',target='background'):
    return dict(type=kind,target_layer=target,blur_pixels=6,start=0,end=1,intensity=.2,center=[.5,.5],radius=.5,color=[.7,.8,.9],reason='The background garden should stay behind the speaking character.')

def test_depth_targets_protect_character_and_source_time():
    p=plan();p['effects']=[depth()];validate_effects(p)
    p['effects'][0]['target_layer']='character'
    with pytest.raises(ValueError,match='never a character'):validate_effects(p)
    p['effects']=[depth()];p['effects'][0]['blur_pixels']=50
    with pytest.raises(ValueError,match='source pixels'):validate_effects(p)

def test_script_requires_actual_separation_and_rejects_uploaded_video():
    raw={'depth_effects':[depth()]}
    assert normalize(raw,{'visual_type':'image'},[{'role':'background'}])[0]['type']=='depth_background_blur'
    with pytest.raises(ValueError,match='separated plane'):normalize(raw,{},[])
    with pytest.raises(ValueError,match='still layers'):normalize(raw,{'visual_type':'video'},[{'role':'background'}])

def test_foreground_occlusion_order_cannot_invert():
    p=plan();p['layers'].append(dict(id='fg',role='foreground',z_index=0));p['effects']=[depth('depth_foreground_blur','fg')]
    with pytest.raises(ValueError,match='occlusion'):validate_effects(p)


def test_no_full_frame_blur_disguised_as_background():
    p=plan();p['layers']=p['layers'][:1];p['effects']=[depth()]
    with pytest.raises(ValueError,match='flattened'):validate_effects(p)


def test_all_scene_mode_cannot_silently_omit_the_finishing_decision():
    scene={'parallax_mode':'all_scenes','visual_type':'image'}
    for raw in ({},{'depth_effects':[]}):
        with pytest.raises(ValueError,match='explicit depth'):normalize(raw,scene,[])
    assert normalize({'depth_effects':[],'depth_effects_reason':'The character and distant sign both need sharp detail.'},scene,[])==[]
    raw={'depth_effects':[depth()],'depth_effects_reason':'Defocus the distant garden without hiding the subject.'}
    assert len(normalize(raw,scene,[{'role':'background'}]))==1


def test_reviewed_effect_cannot_disappear_during_render_binding():
    from depth_finishing import assert_applied
    p=plan();p['effects']=[depth()];assert_applied([depth()],p)
    p['effects']=[]
    with pytest.raises(ValueError,match='dropped'):assert_applied([depth()],p)
