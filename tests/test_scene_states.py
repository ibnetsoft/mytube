"""The real preparation/AE writer paths with deterministic image-generator fixtures."""
import copy
import sys
from pathlib import Path

import pytest
from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'worker'))
from character_states import prepare_scene_states
from ae_scene_animation import write_scene_jsx, validate_plan, apply_scene_state_transitions


def scene_plan():
    return {
        'contract': 'ae_scene/v1', 'schema_version': 'ae_scene/v1', 'timing': 'normalized',
        'width': 128, 'height': 128,
        'camera': [dict(t=t, x=.5, y=.5, scale=1, rotation=0) for t in (0, 1)],
        'layers': [dict(id='bg', role='background', z_index=0), dict(id='object', role='prop', z_index=1)],
        'lights': [], 'transition': {'in': 'cut', 'out': 'cut', 'fraction': 0},
        'continuity': dict(entry='same tree', exit='same tree', screen_direction='left', light_direction='left'),
    }


@pytest.mark.parametrize('story,changes', [
    ('Time passes: full moon becomes half moon.', ['Half moon']),
    ('An apple falls from the branch to the ground.', ['Apple midway down', 'Apple on the ground']),
    ('The empty tree now has a bird perched on it.', ['A bird perched on the branch']),
])
def test_scenery_states_preserve_unedited_pixels_and_reach_ae_writer(tmp_path, story, changes):
    plan = scene_plan()
    original = copy.deepcopy(plan)
    source = tmp_path / 'background.png'
    Image.new('RGBA', (128, 128), 'navy').save(source)
    foreground = tmp_path / 'object.png'
    Image.new('RGBA', (128, 128)).save(foreground)
    files = [{'role': 'layer', 'layer_id': 'bg', 'path': source},
             {'role': 'background_plate', 'path': source},
             {'role': 'layer', 'layer_id': 'object', 'path': foreground}]
    proposal = {'status': 'ready', 'target_layer_id': 'bg', 'subject': story,
                'edit_bounds': [.25, .25, .75, .75],
                'states': [{'start': .3 + .3*i, 'change': change} for i, change in enumerate(changes)]}
    class Runner:
        def _stage(self, identity, stage, context, task):
            assert context['image_layer_ids'] == ['bg', 'object']
            assert 'No character is required' in task
            return proposal
    class Generator:
        calls = 0
        def generate(self, **kwargs):
            assert kwargs['reference'] == source and kwargs['role'] == 'background'
            assert 'Remove its previous appearance/location' in kwargs['prompt']
            self.calls += 1
            output = tmp_path / f'generated-{self.calls}.png'
            # Deliberate drift everywhere: production compositing must remove drift outside bounds.
            Image.new('RGBA', (128, 128), 'orange').save(output)
            return output
    generator = Generator()
    updated, output_files, images = prepare_scene_states(plan, files, {'count': len(changes)+1, 'scene_text': story},
                                                        Runner(), generator, tmp_path)
    assert plan == original and updated['layers'][0] == original['layers'][0]
    assert len(images) == len(changes) == generator.calls
    assert len([l for l in updated['layers'] if l['role'] == 'background']) == 1
    for path in images:
        with Image.open(path) as picture:
            assert picture.getpixel((0, 0)) == (0, 0, 128, 255)
            assert picture.getpixel((32, 64)) == (0, 0, 128, 255)
            assert picture.getpixel((64, 64)) == (255, 165, 0, 255)
    validate_plan(updated)
    jsx = tmp_path / 'scene.jsx'
    paths = {f['layer_id']: f['path'] for f in output_files if f.get('layer_id')}
    write_scene_jsx(updated, paths, tmp_path/'scene.aep', tmp_path/'native.avi', jsx, 4)
    assert 'scene_state_1' in jsx.read_text() and 'ADBE Opacity' in jsx.read_text()
    assert updated['scene_state_plan']['target_layer_id'] == 'bg'
    # The full-image outgoing state must cover the bottom original until the
    # incoming state is opaque, otherwise the old hanging apple reappears.
    from ae_scene_animation import _interpolate
    outgoing = updated['layers'][1]['motion']
    assert _interpolate(outgoing, .31, ('opacity',))['opacity'] == 100
    if len(changes) == 2:
        outgoing = updated['layers'][2]['motion']
        assert _interpolate(outgoing, .61, ('opacity',))['opacity'] == 100


def test_transparent_prop_can_disappear_without_retaining_old_pixels(tmp_path):
    plan = scene_plan()
    source = tmp_path / 'apple.png'
    image = Image.new('RGBA', (128, 128))
    ImageDraw.Draw(image).ellipse((45, 45, 75, 75), fill='red')
    image.save(source)
    empty = tmp_path / 'empty.png'
    Image.new('RGBA', (128, 128)).save(empty)
    class Runner:
        def _stage(self, *args):
            return {'status': 'ready', 'target_layer_id': 'object', 'subject': 'apple',
                    'edit_bounds': [.25, .25, .75, .75], 'states': [{'start': .5, 'change': 'Apple is gone'}]}
    class Generator:
        def generate(self, **kwargs):
            assert kwargs['role'] == 'prop_focus'
            return empty
    result, _, images = prepare_scene_states(plan, [{'role': 'layer', 'layer_id': 'object', 'path': source}],
                                            {'count': 2}, Runner(), Generator(), tmp_path)
    with Image.open(images[0]) as picture:
        assert picture.getchannel('A').getextrema() == (0, 0)
    assert result['layers'][-1]['motion'][-1]['opacity'] == 100


def test_unmotivated_change_does_not_generate_art(tmp_path):
    class Runner:
        def _stage(self, *args):
            return {'status': 'unchanged', 'reason': 'No state change in this shot'}
    plan = scene_plan()
    result, files, images = prepare_scene_states(plan, [], {'count': 2}, Runner(), None, tmp_path)
    assert result['scene_state_plan']['status'] == 'unchanged'
    assert not images and not files and 'scene_state_plan' not in plan


@pytest.mark.parametrize('bounds', [[.8, .2, .1, .7], [0, 0, 2, 1], [0, 0, float('nan'), 1]])
def test_invalid_edit_bounds_fail_before_generation(tmp_path, bounds):
    class Runner:
        def _stage(self, *args):
            return {'status': 'ready', 'target_layer_id': 'bg', 'edit_bounds': bounds}
    with pytest.raises(ValueError, match='bounds'):
        prepare_scene_states(scene_plan(), [{'layer_id': 'bg', 'path': tmp_path/'source.png'}],
                             {'count': 2}, Runner(), None, tmp_path)


def test_object_state_transition_preserves_existing_motion():
    motion = [dict(t=t, x=.02*t, y=0, scale=1, rotation=0, opacity=80) for t in (0, 1)]
    plan = scene_plan()
    plan['layers'][1]['motion'] = motion
    alternate = copy.deepcopy(plan['layers'][1])
    alternate.update(id='alternate', z_index=2)
    plan['layers'].append(alternate)
    updated = apply_scene_state_transitions(plan, [{'layer_id': 'object', 'start': 0}, {'layer_id': 'alternate', 'start': .5}])
    assert updated['layers'][2]['motion'][-1]['x'] == .02
    assert updated['layers'][2]['motion'][-1]['opacity'] == 80
    assert plan['layers'][1]['motion'] == motion


def test_disabled_general_states_are_unchanged():
    plan = scene_plan()
    assert prepare_scene_states(plan, [], None, None, None, None) == (plan, [], [])
