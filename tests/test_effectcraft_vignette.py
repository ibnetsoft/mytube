import copy
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'worker'))
from effectcraft_compatibility import VIGNETTE_MARKER, LIGHT_MASK_MARKER, vignette_replacements, smooth_mask_replacements


def fixture():
    def prop(name, value):
        return dict(match=name, value=dict(v=value))
    mask = dict(kind=dict(mode='Add', inverted=True, feather_falloff='Smooth'), children=[
        prop('path', dict(closed=True, vertices=[[-100, 540], [960, -100], [2000, 540]])),
        prop('feather', [800, 400]), prop('expansion', 0), prop('opacity', 100)])
    layer = dict(id=3, name='ae_effect_subtle_vignette_0', source=dict(item=2),
                 props=dict(children=[dict(match='masks', children=[mask]),
                                      dict(match='effects', children=[]),
                                      dict(match='transform', children=[prop('anchor', [960, 540, 0]),
                                           prop('position', [960, 540, 0]), prop('scale', [100, 100, 100]),
                                           prop('rotation', 0), prop('opacity', 11.25)])]))
    return dict(items={'1':dict(id=1, kind=dict(type='Comp', width=1920, height=1080, layers=[layer])),
                       '2':dict(kind=dict(type='Solid', color=[0, 0, 0], width=1920, height=1080))})


def test_padding_preserves_world_geometry_and_planner_leaves_source_intact():
    p = fixture(); original = copy.deepcopy(p)
    r, = vignette_replacements(p)
    assert p == original
    assert r['native_feather'] == [600, 300]
    for v in [[-100, 540], [960, -100], [2000, 540]]:
        for axis, anchor in enumerate([960, 540]):
            pad = r['padding'][axis]
            assert (v[axis]+pad)-(anchor+pad) == v[axis]-anchor
    assert r['width'] == 1920+2*r['padding'][0]
    assert r['height'] == 1080+2*r['padding'][1]


def test_idempotent_marked_layer_is_skipped():
    p = fixture();p['items']['1']['kind']['layers'][0]['comment'] = VIGNETTE_MARKER
    assert vignette_replacements(p) == []


def test_moving_light_mask_preserves_authored_motion_and_color():
    p = fixture();l = p['items']['1']['kind']['layers'][0]
    l['name'] = 'ae_effect_light_sweep_0'
    l['props']['children'][0]['children'][0]['kind']['inverted'] = False
    position = l['props']['children'][2]['children'][1]
    position['keys'] = [dict(time=0, value=dict(v=[-400,540,0])),dict(time=24, value=dict(v=[960,540,0]))]
    p['items']['2']['kind']['color'] = [1., .82, .55]
    original = copy.deepcopy(p)
    r, = smooth_mask_replacements(p)
    assert r['native_feather'] == [600, 300]
    assert p == original
    assert vignette_replacements(p) == []
    l['comment'] = LIGHT_MASK_MARKER
    assert smooth_mask_replacements(p) == []


@pytest.mark.parametrize('change', ['animated_path', 'animated_feather', 'multiple', 'allocation', 'parent'])
def test_unsupported_vignettes_require_review(change):
    p = fixture();l = p['items']['1']['kind']['layers'][0];m = l['props']['children'][0]['children'][0]
    if change == 'animated_path':m['children'][0]['keys'] = [dict(time=0)]
    elif change == 'animated_feather':m['children'][1]['expression'] = 'time'
    elif change == 'multiple':l['props']['children'][0]['children'].append(copy.deepcopy(m))
    elif change == 'allocation':m['children'][1]['value']['v'] = [100000, 100000]
    else:l['parent'] = 99
    with pytest.raises(ValueError):vignette_replacements(p)
