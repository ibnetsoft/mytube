import copy,sys
from pathlib import Path
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'worker'))
from script_parallax import selection,bind_packages,ROLES

def fixture():
    direction={'ae_operations':['depth_parallax'],'primary_effect':'depth_parallax',
        'dramatic_intent':'Let the foreground branches reveal the waiting character in the scripted garden.',
        'effect_limits':{'max_move_ratio':.02},
        'layer_specs':[{'role':r,'purpose':'Script garden depth '+r,'image_prompt':'Keep exact original composition: '+r} for r in ROLES]}
    return {'scene_number':19,'visual_type':'image','duration_seconds':4,'scene_direction_plan':direction},direction

def test_only_explicit_script_selected_stills_get_registered_three_layer_package():
    scene,direction=fixture();hold={'scene_number':20,'scene_direction_plan':{'ae_operations':['hold']}}
    assert bind_packages([scene,hold])==[19]
    assert scene['parallax_plan']['required_layers']==list(ROLES)
    assert scene['ae_effect_plan']['template']=='parallax_layered_scene'
    assert scene['ae_effect_plan']['asset_requirements']['optional_layers']==[]
    assert scene['parallax_plan']['review_required'] is True
    assert not hold['parallax_plan']['enabled']

@pytest.mark.parametrize('change',[{'scene_number':18},{'visual_type':'video'},{'video_generation_mode':'user_upload'}])
def test_no_second_motion_on_original_video(change):
    scene,direction=fixture();scene.update(change)
    with pytest.raises(ValueError,match='still'):selection(scene,direction)

def test_no_fake_flattened_or_unexplained_layers():
    scene,direction=fixture();direction['layer_specs'][0].pop('image_prompt')
    with pytest.raises(ValueError,match='instructions'):selection(scene,direction)
    scene,direction=fixture();direction['layer_specs'].pop()
    with pytest.raises(ValueError,match='exactly'):selection(scene,direction)

def test_exported_generation_prompt_retains_per_plane_script_instruction():
    import manga_layer_generation as g
    scene,direction=fixture();bind_packages([scene])
    prompt=g._prompt(scene,{'scene_number':19,'template':'parallax_layered_scene'},'foreground',{'sha256':'a'*64})
    assert 'Keep exact original composition: foreground' in prompt
    assert 'exact pixel registration' in prompt


def test_script_selection_forces_real_package_even_without_manual_range_or_credit_ranking():
    from codex_content_runner import _plan_image_generation_efficiency
    from manga_layer_package import scene_spec
    scene,direction=fixture();scene['image_prompt']='A character waits in a garden behind foreground branches.'
    effects=[]
    result=_plan_image_generation_efficiency([scene],{'image_layer_mode':'hybrid'},effects)
    assert scene['psd_layer_plan']['selection_source']=='scene_visual_director'
    assert scene['psd_layer_plan']['method']=='registered_individual_layer_pngs'
    assert scene['psd_layer_plan']['credit_cost_estimate']==3
    assert set(scene_spec(scene,1)['required_layers'])==set(ROLES)
    assert effects[0]['scene_number']==19
    assert result['psd_layer_scene_count']==1


def test_visual_director_normalization_marks_selected_still_and_rejects_video():
    from scene_visual_director import validate_directorial_plans
    scene,direction=fixture()
    raw={**direction,'required_layers':direction['layer_specs'],'visual_strategy':'Reveal the waiting character through the existing branches.',
        'timed_beats':[{'start_seconds':0,'end_seconds':4,'action':'Restrained depth reveal','target':'waiting character'}],
        'qa_assertions':['No holes behind moved character; preserve source layout.']}
    result=validate_directorial_plans([scene],{'scene_directions':[raw]})
    assert result[0]['parallax_plan']['enabled'] is True
    scene['scene_number']=1
    with pytest.raises(ValueError,match='still'):validate_directorial_plans([scene],{'scene_directions':[raw]})


def test_publish_cannot_defer_script_selected_layers(monkeypatch,tmp_path):
    import cowork_scene_assets as publisher
    scene,_=fixture();bind_packages([scene])
    monkeypatch.setattr(publisher,'_manifest',lambda _: {'scene_specs':[scene]})
    monkeypatch.setattr(publisher,'_topic',lambda _: pytest.fail('Must stop before external read/write'))
    with pytest.raises(ValueError,match='requires reviewed separated layers'):publisher.publish(tmp_path/'manifest.json',tmp_path,False,defer_layers=True)
