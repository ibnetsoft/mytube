import copy
import math
import sys
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'worker'))
from effectcraft_compatibility import gaussian_kernel, fractional_replacements, calibrated_gaussian_kernel


def project(tmp_path, amount=.7, alpha=255):
    path = tmp_path / 'layer.png'
    Image.new('RGBA', (12, 12), (100, 120, 140, alpha)).save(path)
    def prop(name, value):
        return {'match': name, 'value': {'t': 'Scalar', 'v': value}}
    effect = {'match': 'ec.blur.gaussian', 'enabled': True, 'children': [
        prop('blurriness', amount), prop('dimensions', 0), prop('repeatEdge', False)]}
    layer = {'name': 'background', 'source': {'type': 'Footage', 'item': 2},
             'props': {'children': [{'match': 'masks', 'children': []},
                                    {'match': 'effects', 'children': [effect]}]}}
    return {'items': {'1': {'id': 1, 'kind': {'type': 'Comp', 'layers': [layer]}},
                      '2': {'kind': {'type': 'Footage', 'kind': 'Still', 'path': str(path)}}}}


def effect(p):
    return p['items']['1']['kind']['layers'][0]['props']['children'][1]['children'][0]


def test_impulse_has_fractional_neighbours_without_amplifying_dc():
    kernel = np.array(gaussian_kernel(.7)).reshape(3, 3)
    # A unit impulse spreads continuously; a uniform image keeps its brightness.
    assert 0 < kernel[1, 0] < kernel[1, 1] < 1
    assert kernel.sum() == pytest.approx(1)
    assert np.array_equal(kernel, kernel[::-1, ::-1])
    assert np.count_nonzero(kernel) == 9
    assert gaussian_kernel(0) == [0, 0, 0, 0, 1, 0, 0, 0, 0]


def test_original_point35_is_not_replaced_by_a_stronger_radius():
    k = gaussian_kernel(.35)
    assert 0 < k[1] < 1e-6
    assert k[4] > .99999
    assert sum(k) == pytest.approx(1)
    assert gaussian_kernel(1e-300) == gaussian_kernel(0)


@pytest.mark.parametrize('dimensions,zero_row', [(1, 0), (2, None)])
def test_directional_kernel(dimensions, zero_row):
    kernel = np.array(gaussian_kernel(.7, dimensions)).reshape(3, 3)
    assert kernel.sum() == pytest.approx(1)
    if zero_row is not None:
        assert not kernel[zero_row].any()
    else:
        assert not kernel[:, 0].any()


def test_preserves_plan_and_selects_only_affected_static_effect(tmp_path):
    p = project(tmp_path)
    before = copy.deepcopy(p)
    result = fractional_replacements(p)
    assert len(result) == 1 and result[0]['amount'] == .7
    assert p == before
    effect(p)['enabled'] = False
    assert fractional_replacements(p) == []
    effect(p)['enabled'] = True
    effect(p)['children'][0]['value']['v'] = 4
    assert fractional_replacements(p) == []


def test_transparent_or_masked_source_fails_instead_of_preserving_wrong_alpha(tmp_path):
    p = project(tmp_path, alpha=128)
    with pytest.raises(ValueError, match='opaque'):
        fractional_replacements(p)
    p = project(tmp_path)
    p['items']['1']['kind']['layers'][0]['props']['children'][0]['children'] = [{}]
    with pytest.raises(ValueError, match='unmasked'):
        fractional_replacements(p)


def test_animated_small_blur_is_not_silently_frozen(tmp_path):
    p = project(tmp_path)
    effect(p)['children'][0]['keys'] = [{'time': 0, 'value': .7}]
    with pytest.raises(ValueError, match='Animated'):
        fractional_replacements(p)


def test_animated_large_gaussian_stays_native(tmp_path):
    p = project(tmp_path, amount=4)
    effect(p)['children'][0]['keys'] = [{'time': 0, 'value': {'t': 'Scalar', 'v': 4}},
                                     {'time': 1, 'value': {'t': 'Scalar', 'v': 8}}]
    assert fractional_replacements(p) == []


def test_calibrated_radius_preserves_amount_and_dc_for_flat_fields(tmp_path):
    p = project(tmp_path, amount=1.2)
    original = copy.deepcopy(p)
    r, = fractional_replacements(p)
    assert r['amount'] == 1.2 and r['working_gamma'] == 2.4
    assert r['method'] == 'measured-ae-1.2-v1'
    k = np.array(r['kernel']).reshape(3, 3)
    assert k.sum() == pytest.approx(1)
    assert np.array_equal(k, k.T) and np.array_equal(k, k[::-1, ::-1])
    for level in [.05, .25, .5, .95]:
        assert ((level**2.4)*k.sum())**(1/2.4) == pytest.approx(level)
    assert p == original


@pytest.mark.parametrize('dimensions', [0, 1, 2])
def test_calibrated_dimensions_preserve_energy(dimensions):
    if dimensions != 0:
        with pytest.raises(ValueError, match='Uncalibrated'):calibrated_gaussian_kernel(1.2, dimensions)
        return
    k = np.array(calibrated_gaussian_kernel(1.2, dimensions)).reshape(3, 3)
    assert k.sum() == pytest.approx(1)


def test_calibration_is_not_extrapolated_or_frozen(tmp_path):
    with pytest.raises(ValueError):calibrated_gaussian_kernel(1.4)
    p = project(tmp_path, amount=1.2)
    effect(p)['children'][0]['keys'] = [{'time':0, 'value':1.2}]
    with pytest.raises(ValueError, match='Animated'):fractional_replacements(p)


@pytest.mark.parametrize('amount', [math.nan, math.inf, -1, 2])
def test_invalid_or_large_kernel_is_rejected(amount):
    with pytest.raises(ValueError):
        gaussian_kernel(amount)
