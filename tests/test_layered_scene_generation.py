from pathlib import Path
from PIL import Image
from worker.layered_scene_generation import generate_scene_planes


class FakeGenerator:
    def __init__(self, root):
        self.root = root
        self.roles = []

    def generate(self, *, prompt, role, reference, work_dir):
        self.roles.append((role, reference))
        path = self.root / f'{len(self.roles)}.png'
        if role == 'background':
            Image.new('RGB', (512, 512), (10, 20, 30)).save(path)
        else:
            image = Image.new('RGBA', (512, 512), (0, 0, 0, 0))
            image.paste((200, 20, 30, 255), (100, 100, 300, 400))
            image.save(path)
        return path


def test_generates_planes_before_composite(tmp_path):
    reference = tmp_path / 'reference.png'
    Image.new('RGB', (2, 2)).save(reference)
    generator = FakeGenerator(tmp_path)
    result = generate_scene_planes({'scene_number': 19, 'image_prompt': 'A person in a room',
        'characters': [{'key': 'person', 'reference_file': str(reference),
                        'placement_prompt': 'center'}]}, tmp_path / 'out', generator=generator)
    assert [role for role, _ in generator.roles] == ['background', 'character']
    assert generator.roles[1][1] == reference
    assert len(result['plane_files']) == 2
    assert Path(result['scene_file']).is_file()
    again = generate_scene_planes({'scene_number': 19, 'image_prompt': 'A person in a room',
        'characters': [{'key': 'person', 'reference_file': str(reference),
                        'placement_prompt': 'center'}]}, tmp_path / 'out', generator=generator)
    assert again['sha256'] == result['sha256']
    assert len(generator.roles) == 2


def test_manifest_selects_only_scoped_scenes_and_resolves_cast(tmp_path):
    from worker.layered_scene_generation import generate_manifest_scenes
    reference = tmp_path / 'reference.png'
    Image.new('RGB', (2, 2)).save(reference)
    generator = FakeGenerator(tmp_path)
    manifest = {'effect_scene_range': {'start': 19, 'end': 20},
        'scene_specs': [{'scene_number': 18, 'image_prompt': 'earlier'},
                        {'scene_number': 19, 'image_prompt': 'A person in a room'},
                        {'scene_number': 51, 'image_prompt': 'later'}],
        'scene_cast': [{'scene_number': 19, 'characters': ['A']}],
        'character_references': [{'name': 'A', 'character_key': 'a', 'local_file': str(reference)}]}
    results = generate_manifest_scenes(manifest, tmp_path / 'out', generator=generator)
    assert [r['scene_number'] for r in results] == [19]
    assert [role for role, _ in generator.roles] == ['background', 'character']


def test_crop_uses_composite_for_scoped_scene(tmp_path, monkeypatch):
    import json
    from worker import cowork_scene_assets as assets
    from worker import layered_scene_generation as layered
    root = tmp_path / 'input'
    out = tmp_path / 'output'
    root.mkdir()
    reference = tmp_path / 'reference.png'
    Image.new('RGB', (8, 8)).save(reference)
    Image.new('RGB', (800, 800), (20, 30, 40)).save(root / 'grid-001.png')
    manifest = {'schema': 'cowork_scene_assets/v1', 'topic_id': 'test', 'effect_scene_range': {'start': 2, 'end': 3},
        'grids': [{'grid_number': 1, 'scene_numbers': [1, 2, 3, 4], 'raw_file': 'grid-001.png'}],
        'scene_specs': [{'scene_number': n, 'image_prompt': f'scene {n}'} for n in range(1, 5)],
        'scene_cast': [{'scene_number': n, 'characters': []} for n in range(1, 5)],
        'character_references': []}
    path = tmp_path / 'manifest.json'
    path.write_text(json.dumps(manifest), encoding='utf-8')
    original = layered.generate_manifest_scenes
    generator = FakeGenerator(tmp_path)
    monkeypatch.setattr(layered, 'generate_manifest_scenes',
                        lambda m, d: original(m, d, generator=generator))
    assets.crop_grids(path, root, out)
    assert all((out / f'scene-{n:03}.png').exists() for n in range(1, 5))
    assert [r for r, _ in generator.roles] == ['background', 'background']
    assert (out / 'scene-002-background.png').exists()


def test_recovery_does_not_request_flat_grids_entirely_inside_effect_range():
    from worker.image_recovery import initialize
    manifest = {'schema': 'cowork_scene_assets/v1', 'effect_scene_range': {'start': 19, 'end': 50},
                'grids': [{'grid_number': 1, 'scene_numbers': [17, 18, 19, 20], 'prompt': 'outside'},
                          {'grid_number': 2, 'scene_numbers': [21, 22, 23, 24], 'prompt': 'inside'},
                          {'grid_number': 3, 'scene_numbers': [49, 50, 51, 52], 'prompt': 'outside'}]}
    state = initialize(manifest)
    assert [job['id'] for job in state['jobs']] == ['grid-001', 'grid-003']


def test_cropped_independent_planes_are_published_with_scene(tmp_path, monkeypatch):
    import json
    from worker import cowork_scene_assets as assets
    from worker import generated_speaker_coordinates as coordinates
    monkeypatch.syspath_prepend(str(Path(assets.__file__).parent))
    from worker import layered_scene_generation as layered
    root, out = tmp_path / 'input', tmp_path / 'output'
    root.mkdir()
    Image.new('RGB', (800, 800), (20, 30, 40)).save(root / 'grid-001.png')
    scenes = [{'scene_number': n, 'scene_text': f'text {n}', 'image_prompt': f'scene {n}'} for n in range(1, 5)]
    manifest = {'schema': 'cowork_scene_assets/v1', 'topic_id': '42', 'bucket': 'scene-bucket',
        'effect_scene_range': {'start': 2, 'end': 3},
        'grids': [{'grid_number': 1, 'scene_numbers': [1, 2, 3, 4], 'raw_file': 'grid-001.png'}],
        'scene_specs': scenes, 'scene_cast': [{'scene_number': n, 'characters': []} for n in range(1, 5)],
        'character_references': []}
    path = tmp_path / 'manifest.json'
    path.write_text(json.dumps(manifest), encoding='utf-8')
    generator = FakeGenerator(tmp_path)
    original = layered.generate_manifest_scenes
    monkeypatch.setattr(layered, 'generate_manifest_scenes', lambda m, d: original(m, d, generator=generator))
    assets.crop_grids(path, root, out)
    monkeypatch.setattr(assets, '_topic', lambda _: ({'id': '42'}, {'scenes': scenes}, 'https://test', {}))
    monkeypatch.setattr(assets, '_upload_gcs_file', lambda local, obj, typ: ('scene-bucket', obj, '/asset/' + obj))
    monkeypatch.setattr(coordinates, 'analyze_published_scenes', lambda *args: None)
    saved = []
    monkeypatch.setattr(assets, '_patch_topic_scene_assets', lambda topic, updates, base, headers: saved.extend(updates))
    assert len(assets.publish(path, out, False)) == 4
    updates = {x['scene_number']: x['asset_patch'] for x in saved}
    assert updates[2]['metadata']['cowork_image_asset']['independent_planes']['assets'][0]['role'] == 'background'
    assert 'independent_planes' not in updates[1]['metadata']['cowork_image_asset']
