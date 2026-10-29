from worker.camera_speed_policy import constrain

def keys(scale):return [{'t':0,'scale':1,'x':.5},{'t':1,'scale':scale,'x':.5}]
def test_slow_scene_length_zoom_is_suppressed_without_changing_original():
    original=keys(1.02);result,changed=constrain(original,18)
    assert changed and result[1]['scale']==1 and original[1]['scale']==1.02

def test_medium_zoom_is_retained():
    result,changed=constrain(keys(1.06),3)
    assert not changed and result[-1]['scale']==1.06

def test_fixed_camera_is_retained():
    result,changed=constrain(keys(1),30)
    assert not changed

def test_short_zoom_with_long_hold_is_allowed():
    k=[{'t':0,'scale':1},{'t':.1,'scale':1},{'t':.3,'scale':1.06},{'t':1,'scale':1.06}]
    result,changed=constrain(k,15)
    assert not changed and result==k
