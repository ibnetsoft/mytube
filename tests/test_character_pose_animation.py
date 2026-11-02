import copy
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "worker"))
import pytest
from worker.ae_scene_animation import apply_character_pose_transitions, resolved_layers


def test_pose_transitions_keep_background_and_fade_only_selected_layers():
    plan={'camera':[{'t':0,'x':.5,'y':.5},{'t':1,'x':.5,'y':.5}], 'layers':[
        {'id':'bg','role':'background','z_index':0},
        {'id':'a','role':'character','z_index':1},
        {'id':'b','role':'character','z_index':2},
        {'id':'c','role':'character','z_index':3}]}
    original=copy.deepcopy(plan)
    result=apply_character_pose_transitions(plan,[{'layer_id':'a','start':0},{'layer_id':'b','start':.35},{'layer_id':'c','start':.7}])
    assert plan==original and result['layers'][0]==original['layers'][0]
    assert result['layers'][1]['motion'][-1]['opacity']==0
    assert result['layers'][2]['motion'][0]['opacity']==0
    assert result['layers'][3]['motion'][-1]['opacity']==100
    assert len(resolved_layers(result))==4


def test_pose_transitions_reject_invalid_layers_and_timing():
    plan={'layers':[{'id':'bg','role':'background'},{'id':'a','role':'character'},{'id':'b','role':'character'}]}
    with pytest.raises(ValueError): apply_character_pose_transitions(plan,[{'layer_id':'bg','start':0},{'layer_id':'b','start':.5}])
    with pytest.raises(ValueError): apply_character_pose_transitions(plan,[{'layer_id':'a','start':0},{'layer_id':'b','start':.99}])
