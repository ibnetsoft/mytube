import copy
import pytest
from services.image_grid_prompts import build_compact_image_grid_prompts, build_image_grid_prompts, validate_image_grid_prompt_readiness


def _scenes(count):
    return [{'scene_order': n, 'scene_summary': f'Scene {n} with a distinct action and setting.'} for n in range(1, count + 1)]


def test_missing_panel_positions_are_persisted_without_mutating_cached_spec():
    spec = {'scene_numbers': [1, 2, 3, 4], 'panels': [
        {'scene_number': n, 'panel_prompt': f'Scene {n}: ' + 'A distinct detailed action with a subject, setting and relevant prop. ' * 2}
        for n in range(1, 5)]}
    original = copy.deepcopy(spec)
    grids = build_compact_image_grid_prompts([spec])
    assert spec == original
    assert [p['position'] for p in grids[0]['panels']] == ['Top-Left', 'Top-Right', 'Bottom-Left', 'Bottom-Right']
    validate_image_grid_prompt_readiness(_scenes(4), grids)


def test_wrong_explicit_panel_positions_are_not_silently_repaired():
    spec = {'scene_numbers': [1, 2, 3, 4], 'panels': [
        {'scene_number': n, 'position': 'Bottom-Right', 'panel_prompt': f'Scene {n}: ' + 'A detailed action, concrete setting and subject. ' * 3}
        for n in range(1, 5)]}
    with pytest.raises(ValueError, match='position mismatch'):
        validate_image_grid_prompt_readiness(_scenes(4), build_compact_image_grid_prompts([spec]))


def test_grid_scene_order_cannot_pass_by_set_coverage_alone():
    grids = build_image_grid_prompts(_scenes(8))
    with pytest.raises(ValueError, match='scene order mismatch'):
        validate_image_grid_prompt_readiness(_scenes(8), list(reversed(grids)))

