"""Offline contract, compositing, integrity and real-media boundary checks."""
import copy
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys

import pytest
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'worker'))
import ae_scene_animation as animation
import ae_scene_production as production


def plan():
    return {'contract': 'ae_scene/v1', 'schema_version': 'ae_scene/v1', 'timing': 'normalized',
            'width': 320, 'height': 180, 'output': {'width': 320, 'height': 180},
            'camera': [{'t': 0, 'x': .5, 'y': .5, 'scale': 1.1, 'rotation': 0},
                       {'t': .5, 'x': .51, 'y': .5, 'scale': 1.13, 'rotation': 0},
                       {'t': 1, 'x': .52, 'y': .5, 'scale': 1.15, 'rotation': 0}],
            'layers': [{'id': 'bg', 'role': 'background', 'z_index': 0, 'parallax': 0},
                       {'id': 'hair', 'role': 'hair', 'z_index': 1, 'parallax': .3,
                        'anchor': [.5, .3], 'bend': {'start': [.5, .3], 'end': [.5, .65],
                        'keys': [{'t': 0, 'angle': 0}, {'t': .4, 'angle': 3}, {'t': 1, 'angle': 0}]}}],
            'lights': [{'color': [1, .9, .7], 'center': [.2, .1], 'radius': .4,
                        'keys': [{'t': 0, 'opacity': 0}, {'t': .7, 'opacity': 5}, {'t': 1, 'opacity': 0}]}],
            'transition': {'in': 'cut', 'out': 'fade', 'fraction': .1},
            'continuity': {'entry': 'girl faces right', 'exit': 'girl faces right, reaction cut',
                           'screen_direction': 'rightward gaze', 'light_direction': 'upper left'}}


def passed(checks):
    return {'passed': True, 'critical_issues': [],
            'checks': [{'id': name, 'passed': True, 'evidence': 'Observed labeled pixels'} for name in checks]}


def package(tmp_path):
    original = tmp_path / 'original.psd'
    original.write_bytes(b'PSD fixture; source parser is tested in preparation suite')
    files = []
    source_paths = {}
    for role, layer_id, color in [('source_preview', None, 'gray'), ('layer', 'bg', 'gray'),
                                  ('layer', 'hair', (0, 0, 0, 0)), ('background_plate', None, 'gray')]:
        path = tmp_path / f'{role}-{layer_id}.png'
        Image.new('RGBA', (320, 180), color).save(path)
        name = path.name
        source_paths[name] = path
        files.append({'role': role, 'layer_id': layer_id, 'gcs_bucket': 'fixtures', 'gcs_path': name,
                      'sha256': production.digest(path)})
    source_paths[original.name] = original
    files.append({'role': 'source_psd', 'gcs_bucket': 'fixtures', 'gcs_path': original.name,
                  'sha256': production.digest(original)})
    source = {'id': 'psd-id', 'metadata': {'sha256': production.digest(original)}}
    result = {'plan': plan(), 'plan_sha256': animation.canonical_plan_sha256(plan()), 'files': files,
              'source_sha256': production.digest(original), 'source_asset_id': 'psd-id',
              'width': 320, 'height': 180, 'review': {'passed': True, 'critical_issues': [],
                  'reviewer': 'local_codex_cli', 'evidence': ['Actual source and prepared layers match'],
                  'source_identity_preserved': True, 'background_complete': True, 'motion_supported': True,
                  'continuity_checked': True, 'source_sha256': production.digest(original),
                  'plan_sha256': animation.canonical_plan_sha256(plan()), 'input_fingerprint': 'current-input'}}
    for role, value in [('plan', result['plan']), ('review', result['review'])]:
        path = tmp_path / (role + '.json')
        path.write_text(json.dumps(value), encoding='utf-8')
        source_paths[path.name] = path
        files.append({'role': role, 'gcs_bucket': 'fixtures', 'gcs_path': path.name,
                      'sha256': production.digest(path)})
    scene = {'number': 1, 'start': 0, 'end': 2, 'ae_scene': {'id': 'prepared-id', 'metadata': {
        'kind': 'ae_scene_preparation', 'state': 'prepared', 'fingerprint': 'current-input',
        'input': {'number': 1, 'source_psd': source}, 'result': result}}}
    return scene, source_paths


def test_normalized_scene_maps_camera_parallax_bend_light_and_fade_to_final_duration(tmp_path):
    p = animation.validate_plan(plan())
    layers = animation.resolved_layers(p)
    assert layers[0]['motion'][-1]['x'] == 0
    assert layers[1]['motion'][-1]['x'] < 0
    jsx = tmp_path / 'scene.jsx'
    animation.write_scene_jsx(p, {'bg': tmp_path / 'bg.png', 'hair': tmp_path / 'hair.png'},
                              tmp_path / 'scene.aep', tmp_path / 'scene.avi', jsx, 7.25)
    text = jsx.read_text()
    runtime = json.loads(text.split(';\n', 1)[0].removeprefix('var S = '))
    assert runtime['duration'] == 7.25
    assert runtime['layers'][1]['bend']['keys'][1]['t'] == .4
    assert 'time*S.duration' in text
    assert 'Math.max(O.width/W,O.height/H)' in text  # no aspect distortion
    assert 'CC Bend It' in text and 'canAddProperty' in text
    assert 'ADBE Mask Feather' in text and 'T.fraction' in text
    assert 'source.layers.add(footage)' in text


@pytest.mark.parametrize('change,expected', [
    (lambda p: p['camera'][-1].update(x=.9), 'outside'),
    (lambda p: p['camera'][-1].update(t=.9), 'complete'),
    (lambda p: p['camera'][-1].update(scale=float('nan')), 'finite'),
    (lambda p: p['layers'][1].update(role='character'), 'hair or cloth'),
    (lambda p: p['layers'][1].update(puppet={'pins': []}), 'Puppet'),
    (lambda p: p['layers'][0].update(parallax=.1), 'intact'),
    (lambda p: p['layers'][1].update(z_index=0), 'stacking'),
    (lambda p: p['lights'][0]['keys'][1].update(opacity=50), 'finite'),
])
def test_unsupported_or_destructive_plans_fail_before_ae(change, expected):
    p = plan()
    change(p)
    with pytest.raises(ValueError, match=expected):
        animation.validate_plan(p)


def test_hash_matches_js_number_serialization_including_small_coordinates():
    value = {'float': 1.0, 'zero': -0.0, 'small': 1e-5, 'tiny': 1e-7, 'large': 1.0000000000000002e20,
             'label': '머리카락', 'values': [False, None, .1]}
    expected = '{"float":1,"label":"머리카락","large":100000000000000020000,"small":0.00001,"tiny":1e-7,"values":[false,null,0.1],"zero":0}'
    assert animation.canonical_plan_sha256(value) == hashlib.sha256(expected.encode()).hexdigest()


def test_preparation_requires_unchanged_source_plan_and_full_opaque_background(tmp_path, monkeypatch):
    scene, remote = package(tmp_path)
    monkeypatch.setattr(production, '_download', lambda bucket, key, path: shutil.copyfile(remote[key], path))
    prepared = production.load_preparation(scene, tmp_path / 'download', lambda: None)
    assert prepared['source_sha256'] == production.digest(remote['original.psd'])
    untagged_upload = copy.deepcopy(scene)
    untagged_upload['ae_scene']['metadata']['input']['source_psd']['metadata'].pop('sha256')
    assert production.load_preparation(untagged_upload, tmp_path / 'download', lambda: None)['source_sha256'] == prepared['source_sha256']
    changed = copy.deepcopy(scene)
    changed['ae_scene']['metadata']['result']['plan']['camera'][1]['scale'] = 1.2
    with pytest.raises(ValueError, match='modified'):
        production.load_preparation(changed, tmp_path / 'changed', lambda: None)
    # A valid digest of an incomplete background is still unsuitable for animation.
    bad = tmp_path / 'hole.png'
    Image.new('RGBA', (320, 180), (1, 2, 3, 0)).save(bad)
    changed = copy.deepcopy(scene)
    entry = next(f for f in changed['ae_scene']['metadata']['result']['files'] if f['role'] == 'background_plate')
    entry.update(gcs_path='hole.png', sha256=production.digest(bad))
    remote['hole.png'] = bad
    with pytest.raises(ValueError, match='unfilled holes'):
        production.load_preparation(changed, tmp_path / 'hole-package', lambda: None)


def test_corrupt_remote_file_is_not_imported(tmp_path, monkeypatch):
    scene, remote = package(tmp_path)
    monkeypatch.setattr(production, '_download', lambda bucket, key, path: path.write_bytes(b'corrupt'))
    with pytest.raises(ValueError, match='checksum mismatch'):
        production.load_preparation(scene, tmp_path / 'download', lambda: None)


def test_review_requires_all_checks_and_rejects_duplicate_or_uncertain_evidence():
    response = passed(production.RENDER_CHECKS)
    assert production.valid_review(response, production.RENDER_CHECKS)
    response['checks'][-1] = response['checks'][0]
    assert not production.valid_review(response, production.RENDER_CHECKS)
    response = passed(production.RENDER_CHECKS)
    response['checks'][0]['evidence'] = ''
    assert not production.valid_review(response, production.RENDER_CHECKS)


def test_visual_sampling_includes_every_authored_action_and_fade():
    times = production.sample_times(plan(), 10)
    assert 4 in times and 7 in times and 9 in times and 9.5 in times
    assert times[0] == 0 and times[-1] == 239 / 24


def test_final_audio_checksum_must_match_before_render(tmp_path):
    audio = tmp_path / 'audio.wav'
    audio.write_bytes(b'new audio')
    scene = {'start': 0, 'end': 2, 'audio': {'metadata': {'sha256': '0' * 64}}}
    with pytest.raises(ValueError, match='narration checksum'):
        production.render_scene(scene, audio, tmp_path, lambda: None, None)


def test_sequence_checks_both_neighbors_and_cannot_fallback_missing_ae_output(tmp_path, monkeypatch):
    from ae_scene_review_contract import sequence_review_matches
    image = tmp_path / 'neighbor.png'
    Image.new('RGB', (320, 180), 'gray').save(image)
    scene = {'number': 2, 'start': 2, 'end': 4, 'ae_scene': {'metadata': {'result': {'plan': plan()}}}}
    others = [{'number': 1, 'start': 0, 'end': 2, 'image': {'id': 'left'}}, scene,
              {'number': 3, 'start': 4, 'end': 6, 'image': {'id': 'right'}}]
    class Reviewer:
        def __init__(self): self.contexts = []
        def _stage(self, identity, stage, context, prompt):
            self.contexts.append(context)
            return passed(production.BOUNDARY_CHECKS)
    reviewer = Reviewer()
    monkeypatch.setattr(production, '_download_asset', lambda asset, target: image)
    monkeypatch.setattr(production, '_boundary_images', lambda *args: ([image], [0.]))
    result = production.review_sequence(others, {2: image}, tmp_path / 'review', lambda: None, reviewer)
    assert [(b['from'], b['to']) for b in result['checked_boundaries']] == [(1, 2), (2, 3)]
    assert all(context['_local_image_paths'] for context in reviewer.contexts)
    assert sequence_review_matches(others, [{'number': 2, 'status': 'artifact_ready',
                                            'render_sha256': production.digest(image)}], result)
    with pytest.raises(ValueError, match='no rendered output'):
        production.review_sequence(others, {}, tmp_path / 'missing', lambda: None, reviewer)


def test_boundary_review_failure_blocks_sequence(tmp_path, monkeypatch):
    image = tmp_path / 'frame.png'
    Image.new('RGB', (32, 32), 'gray').save(image)
    scenes = [{'number': n, 'start': n, 'end': n + 1, 'ae_scene': {'id': 'prep'}} for n in (1, 2)]
    monkeypatch.setattr(production, '_boundary_images', lambda *args: ([image], [0.]))
    class Reject:
        def _stage(self, *args): return {'passed': False, 'critical_issues': ['identity changed'], 'checks': []}
    with pytest.raises(ValueError, match='continuity review needs repair'):
        production.review_sequence(scenes, {1: image, 2: image}, tmp_path / 'review', lambda: None, Reject())


def test_sequence_skips_zero_duration_slots_like_final_render(tmp_path, monkeypatch):
    image = tmp_path / 'frame.png'
    Image.new('RGB', (32, 32), 'gray').save(image)
    scenes = [{'number': 1, 'start': 0, 'end': 2, 'ae_scene': {'id': 'prep'}},
              {'number': 2, 'start': 2, 'end': 2, 'original_video': {'id': 'omitted'}},
              {'number': 3, 'start': 2, 'end': 4, 'image': {'id': 'actual-next'}}]
    def download(asset, target):
        assert asset['id'] == 'actual-next'
        return image
    monkeypatch.setattr(production, '_download_asset', download)
    monkeypatch.setattr(production, '_boundary_images', lambda *args: ([image], [0.]))
    class Reviewer:
        def _stage(self, *args): return passed(production.BOUNDARY_CHECKS)
    receipt = production.review_sequence(scenes, {1: image}, tmp_path / 'review', lambda: None, Reviewer())
    assert [(entry['from'], entry['to']) for entry in receipt['checked_boundaries']] == [(1, 3)]
    scenes[1]['ae_scene'] = {'id': 'impossible'}
    with pytest.raises(ValueError, match='no final screen time'):
        production.review_sequence(scenes, {1: image}, tmp_path / 'review', lambda: None, Reviewer())


def test_real_video_frames_and_exact_duration_are_read_without_adobe(tmp_path):
    video = tmp_path / 'two-seconds.mp4'
    production.run([production.ffmpeg(), '-v', 'error', '-y', '-f', 'lavfi', '-i',
                    'color=c=gray:s=320x180:r=24:d=2', '-c:v', 'libx264', '-pix_fmt', 'yuv420p', str(video)])
    info = production._video_info(video)
    assert info == {'fps': 24., 'frames': 48, 'duration': 2., 'width': 320, 'height': 180}
    frame = production._frame(video, 47 / 24, tmp_path / 'last.png')
    assert Image.open(frame).size == (320, 180)


def test_real_media_receipt_created_by_renderer_matches_gate_with_native_ae_stub(tmp_path, monkeypatch):
    from ae_scene_review_contract import render_review_matches
    scene, remote = package(tmp_path)
    scene.update(start=.5, end=2.5)
    audio = tmp_path / 'final-recording.wav'
    production.run([production.ffmpeg(), '-v', 'error', '-y', '-f', 'lavfi', '-i',
                    'sine=frequency=440:duration=4', '-c:a', 'pcm_s16le', str(audio)])
    scene['audio'] = {'id': 'final-audio-id', 'metadata': {'sha256': production.digest(audio)}}
    monkeypatch.setattr(production, '_download', lambda bucket, key, path: shutil.copyfile(remote[key], path))
    calls = []
    def native_stub(prepared, directory, duration):
        calls.append(duration)
        video = directory / 'stub-native.mp4'
        production.run([production.ffmpeg(), '-v', 'error', '-y', '-f', 'lavfi', '-i',
                        f'color=c=gray:s=320x180:r=24:d={duration}', '-c:v', 'libx264', str(video)])
        return video
    monkeypatch.setattr(production, '_render_native', native_stub)
    class Reviewer:
        def _stage(self, identity, stage, context, prompt):
            assert context['_local_image_paths'] and all(Path(path).is_file() for path in context['_local_image_paths'])
            assert context['audio_evidence']['source_audio_id'] == 'final-audio-id'
            return passed(production.RENDER_CHECKS)
    result = production.render_scene(scene, audio, tmp_path / 'render', lambda: None, Reviewer())
    review = result['review']
    assert render_review_matches(scene, scene['audio'], review, result['render_sha256'])
    assert review['audio']['source_samples'] == 16000
    assert review['audio']['correlation'] >= .99
    assert review['source_preview_sha256'] == production.digest(remote['source_preview-None.png'])
    cached = production.render_scene(scene, audio, tmp_path / 'render', lambda: None, Reviewer())
    assert cached['render_sha256'] == result['render_sha256'] and calls == [2.]
