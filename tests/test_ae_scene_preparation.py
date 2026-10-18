import copy
import json
import pathlib
import sys

import pytest
from PIL import Image, ImageDraw

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'worker'))
import ae_scene_preparation as prep


def plan():
    return {'contract': 'ae_scene/v1', 'schema_version': 'ae_scene/v1', 'timing': 'normalized',
        'width': 128, 'height': 128,
        'camera': [dict(t=t, x=.5, y=.5, scale=1, rotation=0) for t in (0, 1)],
        'layers': [dict(id='background', role='background', z_index=0, parallax=0,
                        anchor=[.5, .5], source_ids=['psd-001']),
                   dict(id='character', role='character', z_index=1, parallax=0,
                        anchor=[.5, .5], source_ids=['psd-002'])],
        'lights': [], 'transition': {'in': 'cut', 'out': 'cut', 'fraction': 0},
        'continuity': {'entry': 'Character watches left.', 'exit': 'Same pose.',
                       'screen_direction': 'Left.', 'light_direction': 'Upper left.'},
        'qa_assertions': ['Preserve the original face and brushwork.']}


def create_psd(directory, background_hole=False):
    psd_tools = pytest.importorskip('psd_tools')
    from psd_tools.api.layers import PixelLayer
    psd = psd_tools.PSDImage.new('RGBA', (128, 128))
    background = Image.new('RGBA', (128, 128), (50, 80, 110, 255))
    if background_hole:
        ImageDraw.Draw(background).rectangle((48, 48, 80, 80), fill=(0, 0, 0, 0))
    PixelLayer.frompil(background, psd, 'background')
    character = Image.new('RGBA', (128, 128))
    ImageDraw.Draw(character).rectangle((40, 40, 90, 100), fill=(200, 100, 40, 255))
    PixelLayer.frompil(character, psd, 'character')
    source = directory / 'source.psd'
    psd.save(source)
    return source


def review():
    return {'passed': True, 'critical_issues': [], 'evidence': ['Original orange shape is preserved.'],
            'source_identity_preserved': True, 'background_complete': True,
            'motion_supported': True, 'continuity_checked': True}


class Runner:
    def __init__(self, approved=True):
        self.calls = []
        self.approved = approved

    def _stage(self, identity, name, context, task):
        self.calls.append((name, context))
        assert context['_local_image_paths']
        assert all(pathlib.Path(path).is_file() for path in context['_local_image_paths'])
        if name == '02_ae_scene_direction':
            return {'status': 'ready', 'plan': plan(),
                    'background': {'mode': 'reuse', 'reason': 'Complete original background.', 'missing_body_art': []}}
        return {**review(), 'passed': self.approved}


class NoGeneration:
    def generate(self, **kwargs):
        raise AssertionError('Complete original backgrounds must not be regenerated')


def test_psd_import_preserves_source_group_order_and_pixel_reconstruction(tmp_path):
    source = create_psd(tmp_path)
    catalog = prep.import_psd(source, tmp_path / 'catalog')
    assert [(n['id'], n['name']) for n in catalog['nodes']] == [('psd-001', 'background'), ('psd-002', 'character')]
    assert catalog['nodes'][0]['opaque'] is True
    files = prep.selected_layers(plan(), catalog, tmp_path)
    check = prep.reconstruction_check(files, catalog['preview'], (128, 128))
    assert check['mean_pixel_error'] == 0
    assert len(catalog['contact_sheets']) == 1


def test_moving_layers_cannot_duplicate_omit_or_reorder_source_art(tmp_path):
    catalog = prep.import_psd(create_psd(tmp_path), tmp_path / 'catalog')
    duplicated = plan()
    duplicated['layers'][1]['source_ids'] = ['psd-001']
    with pytest.raises(ValueError, match='중복'):
        prep.selected_layers(duplicated, catalog, tmp_path)
    omitted = plan()
    omitted['layers'] = omitted['layers'][:1]
    with pytest.raises(ValueError, match='누락'):
        prep.selected_layers(omitted, catalog, tmp_path)
    reversed_plan = plan()
    reversed_plan['layers'][0]['source_ids'], reversed_plan['layers'][1]['source_ids'] = ['psd-002'], ['psd-001']
    with pytest.raises(ValueError, match='순서'):
        prep.selected_layers(reversed_plan, catalog, tmp_path)


def test_reconstruction_rejects_altered_original_pixels(tmp_path):
    source = tmp_path / 'original.png'
    altered = tmp_path / 'altered.png'
    Image.new('RGBA', (128, 128), 'red').save(source)
    Image.new('RGBA', (128, 128), 'blue').save(altered)
    with pytest.raises(ValueError, match='원본과 다릅니다'):
        prep.reconstruction_check([{'path': altered}], source, (128, 128))


def test_opaque_background_reused_and_missing_body_never_generated(tmp_path):
    catalog = prep.import_psd(create_psd(tmp_path), tmp_path / 'catalog')
    files = prep.selected_layers(plan(), catalog, tmp_path)
    output = prep.background_plate(plan(), files, catalog,
        {'mode': 'reuse', 'missing_body_art': []}, NoGeneration(), tmp_path, lambda: None)
    assert output['generated'] is False
    assert prep.sha256(output['path']) == prep.sha256(files[0]['path'])
    with pytest.raises(ValueError, match='신체'):
        prep.background_plate(plan(), files, catalog,
            {'mode': 'reuse', 'missing_body_art': ['neck behind moving hair']}, NoGeneration(), tmp_path, lambda: None)


def test_background_generation_changes_only_original_transparency(tmp_path):
    catalog = prep.import_psd(create_psd(tmp_path, background_hole=True), tmp_path / 'catalog')
    files = prep.selected_layers(plan(), catalog, tmp_path)
    generated = tmp_path / 'generated.png'
    Image.new('RGBA', (512, 512), (150, 120, 90, 255)).save(generated)
    class Generator:
        def generate(self, **kwargs):
            assert kwargs['role'] == 'background'
            assert kwargs['reference'] == catalog['preview']
            return generated
    output = prep.background_plate(plan(), files, catalog,
        {'mode': 'inpaint', 'reason': 'The original background has a character-shaped hole.', 'missing_body_art': []},
        Generator(), tmp_path, lambda: None)
    with Image.open(output['path']) as image:
        assert image.getpixel((10, 10)) == (50, 80, 110, 255)
        assert image.getpixel((60, 60)) == (150, 120, 90, 255)
        assert image.getchannel('A').getextrema() == (255, 255)


def test_preparation_requires_actual_visual_review_and_hashes_cache(tmp_path):
    source = create_psd(tmp_path)
    snapshot = {'source_psd': {'id': 'source-id'}, 'number': 1}
    runner = Runner()
    result = prep.prepare(source, snapshot, tmp_path / 'prepared', runner, NoGeneration())
    assert result['source_sha256'] == prep.sha256(source)
    assert result['source_asset_id'] == 'source-id'
    assert result['review']['reviewer'] == 'local_codex_cli'
    assert {item['role'] for item in result['files']} >= {'layer', 'source_psd', 'source_preview', 'background_plate', 'plan', 'review'}
    assert len(runner.calls) == 2
    cached = prep.prepare(source, snapshot, tmp_path / 'prepared', runner, NoGeneration())
    assert len(runner.calls) == 2
    assert result['plan_sha256'] == cached['plan_sha256']
    Image.new('RGBA', (128, 128), 'black').save(next(item['path'] for item in result['files'] if item['role'] == 'layer'))
    prep.prepare(source, snapshot, tmp_path / 'prepared', runner, NoGeneration())
    assert len(runner.calls) == 4  # A damaged artifact cannot inherit its prior review.


def test_failed_review_cannot_publish_or_cache_a_prepared_scene(tmp_path):
    source = create_psd(tmp_path)
    with pytest.raises(ValueError, match='검수'):
        prep.prepare(source, {'source_psd': {'id': 'source'}, 'number': 1},
                     tmp_path / 'prepared', Runner(approved=False), NoGeneration())
    assert not (tmp_path / 'prepared' / 'prepared-receipt.json').exists()


def test_structural_director_error_gets_one_bounded_repair_not_blind_approval(tmp_path):
    class RepairRunner(Runner):
        def _stage(self, identity, name, context, task):
            response = super()._stage(identity, name, context, task)
            if name == '02_ae_scene_direction' and 'structural_repair' not in context:
                response['plan']['camera'][0]['scale'] = -1
            return response
    runner = RepairRunner()
    result = prep.prepare(create_psd(tmp_path), {'source_psd': {'id': 'source'}, 'number': 1},
                          tmp_path / 'prepared', runner, NoGeneration())
    assert result['review']['passed'] is True
    assert [name for name, _ in runner.calls] == ['02_ae_scene_direction', '02_ae_scene_direction', '03_ae_scene_preparation_review']
    assert 'structural_repair' in runner.calls[1][1]


def test_reference_image_is_downloaded_as_actual_pixels_and_checks_checksum(tmp_path):
    reference = tmp_path / 'reference.png'
    Image.new('RGB', (128, 128), 'orange').save(reference)
    snapshot = {'number': 1, 'reference_image': {'id': 'image',
        'metadata': {'gcs_bucket': 'bucket', 'gcs_path': 'reference.png', 'sha256': prep.sha256(reference)}}}
    destination = tmp_path / 'inputs'
    destination.mkdir()
    def download(bucket, path, target):
        assert bucket == 'bucket' and path == 'reference.png'
        target.write_bytes(reference.read_bytes())
    result = prep.download_references(snapshot, destination, download)
    assert result[0]['sha256'] == prep.sha256(reference)
    with Image.open(result[0]['images'][0]) as image:
        assert image.getpixel((10, 10)) == (255, 165, 0)
    snapshot['reference_image']['metadata']['sha256'] = '0' * 64
    with pytest.raises(ValueError, match='검증값'):
        prep.download_references(snapshot, destination, download)


def fixture_job():
    source = {'id': 'source', 'asset_type': 'original', 'file_name': 'art.psd', 'mime_type': 'image/vnd.adobe.photoshop',
              'metadata': {'gcs_bucket': 'bucket', 'gcs_path': 'art.psd'}}
    context = {'scene_number': 1, 'scene_title': 'Scene', 'scene_text': 'Hello', 'image_prompt': 'A person', 'video_prompt': ''}
    snapshot = {'number': 1, 'source_psd': source, 'scene_context': context, 'neighbors': [], 'direction_text': 'Slow approach.'}
    fingerprint = prep.canonical_hash(snapshot)
    asset = {'id': 'job', 'status': 'uploaded', 'scene_number': 1, 'created_at': '2026-10-17T10:00:00Z',
             'metadata': {'kind': 'ae_scene_preparation', 'enabled': True, 'fingerprint': fingerprint, 'input': snapshot}}
    original = {**copy.deepcopy(source), 'status': 'uploaded', 'scene_number': 1, 'created_at': '2026-10-17T09:00:00Z'}
    return snapshot, fingerprint, [{'id': 'project', 'status': 'draft'}], [asset, original], [context]


def test_current_guard_accepts_stable_reference_and_rejects_disabled_replacement_script(tmp_path):
    snapshot, identity, projects, assets, scenes = fixture_job()
    assert prep.input_is_current(snapshot, 'job', identity, projects, assets, scenes)
    assets[1]['metadata']['unrelated_coordinate_progress'] = 90
    assert prep.input_is_current(snapshot, 'job', identity, projects, assets, scenes)
    new = {'id': 'disabled', 'status': 'uploaded', 'scene_number': 1, 'created_at': '2026-10-17T11:00:00Z',
           'metadata': {'kind': 'ae_scene_preparation', 'enabled': False, 'state': 'disabled'}}
    assert not prep.input_is_current(snapshot, 'job', identity, projects, [*assets, new], scenes)
    changed = copy.deepcopy(scenes)
    changed[0]['scene_text'] = 'Changed.'
    assert not prep.input_is_current(snapshot, 'job', identity, projects, assets, changed)
    replaced = copy.deepcopy(assets)
    replaced.append({**replaced[1], 'id': 'new-psd', 'created_at': '2026-10-17T11:00:00Z'})
    assert not prep.input_is_current(snapshot, 'job', identity, projects, replaced, scenes)


def test_current_guard_detects_new_neighbor_and_new_reference_video():
    snapshot, identity, projects, assets, scenes = fixture_job()
    assert not prep.input_is_current(snapshot, 'job', identity, projects, assets,
        [*scenes, {'scene_number': 2, 'scene_title': 'New scene'}])
    video = {'id': 'video', 'asset_type': 'video', 'status': 'uploaded', 'scene_number': 1,
             'created_at': '2026-10-17T11:00:00Z', 'metadata': {'gcs_path': 'new.mp4'}}
    assert not prep.input_is_current(snapshot, 'job', identity, projects, [*assets, video], scenes)


def test_project_authored_scene_fallback_matches_web_projection():
    snapshot, identity, projects, assets, scenes = fixture_job()
    projects[0]['project_payload'] = {'structure': {'scenes': [scenes[0]]}}
    assert prep.input_is_current(snapshot, 'job', identity, projects, assets, [{'scene_number': 1}])


def test_canonical_hash_matches_javascript_integer_numbers():
    assert prep.canonical_hash({'b': 1.0, 'a': '한글'}) == prep.canonical_hash({'a': '한글', 'b': 1})
    with pytest.raises(ValueError):
        prep.canonical_hash({'bad': float('nan')})


def test_supervisor_has_one_cross_platform_preparation_role():
    import local_media_supervisor
    command = local_media_supervisor.role_command('preparation')
    assert command[-1] == '--once'
    assert command[-2].endswith('ae_scene_preparation.py')


def test_web_requested_effects_survive_preparation_and_missing_effects_require_repair(tmp_path):
    from test_ae_scene_effects import effect

    class EffectRunner(Runner):
        def __init__(self, include=True):
            super().__init__()
            self.include = include

        def _stage(self, identity, name, context, task):
            result = super()._stage(identity, name, context, task)
            if name == '02_ae_scene_direction' and self.include:
                result['plan']['effects'] = [effect()]
            return result

    source = create_psd(tmp_path)
    snapshot = {'number': 1, 'source_psd': {'id': 'psd'}, 'requested_effects': ['focus_glow']}
    result = prep.prepare(source, snapshot, tmp_path / 'good', EffectRunner(), NoGeneration())
    assert result['plan']['effects'][0]['type'] == 'focus_glow'
    with pytest.raises(ValueError, match='exactly match'):
        prep.prepare(source, snapshot, tmp_path / 'missing', EffectRunner(False), NoGeneration())
