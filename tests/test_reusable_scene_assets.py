import copy
import json
from pathlib import Path
import pytest
from PIL import Image
from worker.reusable_scene_assets import VERSION, validate_plan, generate
from tests.test_layered_scene_generation import FakeGenerator


def manifest(tmp_path):
    ref=tmp_path/'ref.png';Image.new('RGB',(512,512),'red').save(ref)
    return {'schema':'cowork_scene_assets/v1','topic_id':'1','effect_scene_range':{'start':19,'end':50},
      'character_references':[{'name':'A','character_key':'a','local_file':str(ref)}],
      'scene_specs':[{'scene_number':n,'image_prompt':'room'} for n in (51,52,53)],
      'scene_cast':[{'scene_number':n,'characters':['A']} for n in (51,52,53)],
      'grids':[{'grid_number':1,'scene_numbers':[51,52,53,53],'prompt':'old','raw_file':'missing.png'}],
      'reusable_scene_assets':{'version':VERSION,
       'backgrounds':[{'id':'room','prompt':'empty room daylight'},{'id':'street','prompt':'empty street daylight'}],
       'poses':[{'id':'standing','character_key':'a','prompt':'standing left'}],
       'scenes':[{'scene_number':51,'background':'room','poses':['standing']},
                 {'scene_number':52,'background':'street','poses':['standing']},
                 {'scene_number':53,'background':'room','poses':['standing']}]}}


def test_shared_assets_generated_once_and_resume_uses_pixels(tmp_path):
    m=manifest(tmp_path);g=FakeGenerator(tmp_path)
    results=generate(m,tmp_path/'out',generator=g)
    assert len(results)==3 and len(g.roles)==3
    assert [r for r,_ in g.roles]==['background','background','character']
    generate(m,tmp_path/'out',generator=g)
    assert len(g.roles)==3
    assert Path(results[0]['scene_file']).read_bytes()==Path(results[2]['scene_file']).read_bytes()
    shared=next((tmp_path/'out'/'shared-assets').glob('*.png'))
    shared.write_bytes(b'changed')
    with pytest.raises(ValueError,match='bytes changed'):generate(m,tmp_path/'out',generator=g)


@pytest.mark.parametrize('fault',['missing','early','cast','unknown','duplicate'])
def test_plan_cannot_drop_scenes_or_change_cast(tmp_path,fault):
    m=manifest(tmp_path);p=copy.deepcopy(m['reusable_scene_assets'])
    if fault=='missing':p['scenes'].pop()
    if fault=='early':p['scenes'][0]['scene_number']=50
    if fault=='cast':p['scenes'][0]['poses']=[]
    if fault=='unknown':p['scenes'][0]['poses']=['unknown']
    if fault=='duplicate':p['scenes'][0]['poses']=['standing','standing']
    with pytest.raises(ValueError):validate_plan(p,m['scene_specs'],m['character_references'],m['scene_cast'])


def test_crop_skips_post50_grid_and_composes_shared_assets(tmp_path,monkeypatch):
    from worker import cowork_scene_assets as assets, reusable_scene_assets as shared
    from worker.image_recovery import initialize
    m=manifest(tmp_path)
    assert initialize(m)['jobs']==[]
    path=tmp_path/'manifest.json';path.write_text(json.dumps(m))
    original=shared.generate;g=FakeGenerator(tmp_path)
    monkeypatch.setattr(shared,'generate',lambda m,d:original(m,d,generator=g))
    written=assets.crop_grids(path,tmp_path/'missing-input',tmp_path/'out')
    assert {p.name for p in written}=={'scene-051.png','scene-052.png','scene-053.png'}
    assert len(g.roles)==3


def test_deferred_effect_still_and_post50_reuse_share_one_grid(tmp_path,monkeypatch):
    from worker import cowork_scene_assets as assets, reusable_scene_assets as shared
    from worker.image_recovery import initialize
    m=manifest(tmp_path)
    m['layer_production_stage']='post_submission'
    m['scene_specs'].insert(0,{'scene_number':19,'image_prompt':'deferred effect scene'})
    m['scene_cast'].insert(0,{'scene_number':19,'characters':['A']})
    m['grids'][0].update(scene_numbers=[19,51,52,53],raw_file='grid.png')
    assert [job['id'] for job in initialize(m)['jobs']]==['grid-001']
    source=tmp_path/'input';source.mkdir()
    Image.new('RGB',(800,800),(20,30,40)).save(source/'grid.png')
    path=tmp_path/'manifest.json';path.write_text(json.dumps(m))
    original=shared.generate;g=FakeGenerator(tmp_path)
    monkeypatch.setattr(shared,'generate',lambda m,d:original(m,d,generator=g))
    written=assets.crop_grids(path,source,tmp_path/'out')
    assert {p.name for p in written}=={'scene-019.png','scene-051.png','scene-052.png','scene-053.png'}
    assert len(g.roles)==3
    assert not list((tmp_path/'out').glob('*-planes.json'))


def test_export_crop_resume_publish_preserves_deferred_layers(tmp_path, monkeypatch):
    """Real exported settings survive recovery/cropping and flat-image publishing."""
    from worker import cowork_scene_assets as assets, reusable_scene_assets as shared
    from worker import image_recovery as recovery, generated_speaker_coordinates as coordinates
    monkeypatch.syspath_prepend(str(Path(assets.__file__).parent))
    m = manifest(tmp_path)
    scenes = [{'scene_number': 19, 'image_prompt': 'earlier action',
               'local_layer_plan': {'enabled': True}}, *m['scene_specs']]
    structure = {'scenes': scenes, 'scene_cast': [{'scene_number': 19, 'characters': ['A']}, *m['scene_cast']],
                 'effect_scene_range': m['effect_scene_range'], 'layer_production_stage': 'post_submission',
                 'reusable_scene_assets': m['reusable_scene_assets'],
                 'character_anchors': {'main_character': {'name': 'A', 'character_key': 'a',
                     'image_url': '/reference.png', 'gcs_path': 'reference.png'}},
                 'image_grid_prompts': [{'grid_number': 1, 'scene_numbers': [19, 51, 52, 53], 'prompt': 'four scenes'}]}
    monkeypatch.setattr(assets, '_topic', lambda _: ({'id': 1}, structure, 'https://test', {}))
    monkeypatch.setattr(assets, '_download_gcs_bytes', lambda *args: Path(m['character_references'][0]['local_file']).read_bytes())
    path = tmp_path/'export'/'manifest.json'
    assets.export_manifest('1', path, 'scene-bucket')
    exported = json.loads(path.read_text())
    assert exported['layer_production_stage'] == 'post_submission'
    assert exported['reusable_scene_assets'] == m['reusable_scene_assets']
    assert 'deferred' in exported['layer_package_instruction']
    grid = tmp_path/'grid.png'; Image.new('RGB', (800, 800), (20, 30, 40)).save(grid)
    state_path = recovery.state_path(path)
    state = json.loads(state_path.read_text())
    for event in ({'action': 'start'}, {'action': 'result', 'outcome': 'generated', 'image_file': str(grid)},
                  {'action': 'accept', 'visual_review': 'Synthetic fixture review only'}):
        state = recovery.transition(state, {'job_id': 'grid-001', **event})
    state_path.write_text(json.dumps(state))
    original = shared.generate; generator = FakeGenerator(tmp_path)
    monkeypatch.setattr(shared, 'generate', lambda m, d: original(m, d, generator=generator))
    out = tmp_path/'out'
    assets.crop_grids(path, tmp_path/'unused', out)
    original_bytes = {p.name: p.read_bytes() for p in out.glob('scene-*.png')}
    assets.crop_grids(path, tmp_path/'unused', out)
    assert {p.name: p.read_bytes() for p in out.glob('scene-*.png')} == original_bytes
    assert len(generator.roles) == 3  # Two backgrounds and one pose, reused for three scenes.
    assert len(json.loads((out/'crop-receipt.json').read_text())['files']) == 4
    monkeypatch.setattr(assets, '_upload_gcs_file', lambda local, obj, typ: ('scene-bucket', obj, '/asset/'+obj))
    monkeypatch.setattr(coordinates, 'analyze_published_scenes', lambda *args: None)
    monkeypatch.setattr(assets, '_write_depth_proxy_layers', lambda *args: pytest.fail('Layers must remain deferred'))
    saved = []
    monkeypatch.setattr(assets, '_patch_topic_scene_assets', lambda topic, updates, base, headers: saved.extend(updates))
    assert len(assets.publish(path, out, False)) == 4
    assert len(saved) == 4
    assert not list(out.glob('*-planes.json'))
    structure['reusable_scene_assets'] = copy.deepcopy(structure['reusable_scene_assets'])
    structure['reusable_scene_assets']['backgrounds'][0]['prompt'] = 'changed room'
    with pytest.raises(ValueError, match='plan changed'):
        assets.publish(path, out, False)


def optional_manifest(tmp_path, *, standalone=True):
    from worker.reusable_scene_assets import OPTIONAL_VERSION
    m = manifest(tmp_path)
    m.pop('effect_scene_range')
    m['layer_production_stage'] = 'post_submission'
    m['scene_specs'] = [{'scene_number': n, 'image_prompt': 'scene',
                         'visual_type': 'video' if n == 4 else 'image'} for n in range(1, 5)]
    m['scene_cast'] = [{'scene_number': n, 'characters': ['A']} for n in range(1, 5)]
    m['grids'] = [{'grid_number': 1, 'scene_numbers': [1, 2, 3, 3], 'prompt': 'scene grid', 'raw_file': 'grid.png'}]
    m['reusable_scene_assets']['version'] = OPTIONAL_VERSION
    m['reusable_scene_assets']['scenes'] = [
        {'scene_number': n, 'mode': 'compose', 'reuse_check': 'Same room, lighting and standing pose',
         'background': 'room', 'poses': ['standing']} for n in (1, 2, 3)]
    if standalone:
        m['reusable_scene_assets']['scenes'][2] = {
            'scene_number': 3, 'mode': 'standalone', 'reuse_check': 'Unique close interaction needs complete new art'}
    return m


def test_optional_reuse_before_51_leaves_unique_scene_on_normal_path(tmp_path, monkeypatch):
    from worker import cowork_scene_assets as assets, reusable_scene_assets as shared, image_recovery as recovery
    m = optional_manifest(tmp_path)
    assert shared.scene_numbers(m) == {1, 2}
    state = recovery.initialize(m)
    grid = tmp_path/'grid.png'; Image.new('RGB', (800, 800), 'blue').save(grid)
    for event in ({'action': 'start'}, {'action': 'result', 'outcome': 'generated', 'image_file': str(grid)},
                  {'action': 'accept', 'visual_review': 'Synthetic fixture only'}):
        state = recovery.transition(state, {'job_id': 'grid-001', **event})
    path = tmp_path/'manifest.json'; path.write_text(json.dumps(m))
    recovery.state_path(path).write_text(json.dumps(state))
    original = shared.generate; generator = FakeGenerator(tmp_path)
    monkeypatch.setattr(shared, 'generate', lambda m, d: original(m, d, generator=generator))
    out = tmp_path/'out'
    assets.crop_grids(path, tmp_path, out)
    assert len(generator.roles) == 2  # One background and one pose serve scenes 1 and 2.
    assert (out/'scene-001.png').read_bytes() == (out/'scene-002.png').read_bytes()
    assert (out/'scene-003.png').read_bytes() != (out/'scene-001.png').read_bytes()
    assert not (out/'scene-003-shared.json').exists()
    assert not (out/'scene-004.png').exists()  # Uploaded video is preserved.


def test_all_compositions_without_effect_range_need_no_flat_grid(tmp_path, monkeypatch):
    from worker import cowork_scene_assets as assets, reusable_scene_assets as shared, image_recovery as recovery
    m = optional_manifest(tmp_path, standalone=False)
    state = recovery.initialize(m)
    assert state['jobs'] == []
    assert recovery.recipes(state, m) == []
    path = tmp_path/'manifest.json'; path.write_text(json.dumps(m))
    recovery.state_path(path).write_text(json.dumps(state))
    original = shared.generate; generator = FakeGenerator(tmp_path)
    monkeypatch.setattr(shared, 'generate', lambda m, d: original(m, d, generator=generator))
    assert len(assets.crop_grids(path, tmp_path/'absent', tmp_path/'out')) == 3
    assert len(generator.roles) == 2


def test_zero_reuse_is_valid_and_generates_no_shared_assets(tmp_path):
    from worker.reusable_scene_assets import scene_numbers
    m = optional_manifest(tmp_path)
    p = m['reusable_scene_assets']
    p['backgrounds'] = []; p['poses'] = []
    p['scenes'] = [{'scene_number': n, 'mode': 'standalone', 'reuse_check': 'Unique shot, no compatible match'}
                   for n in (1, 2, 3)]
    assert scene_numbers(m) == set()
    assert generate(m, tmp_path/'out', generator=FakeGenerator(tmp_path)) == []
    assert not (tmp_path/'out').exists()


@pytest.mark.parametrize('fault', ['unchecked', 'missing', 'video', 'forced_assets'])
def test_optional_plan_requires_all_still_checks_but_no_video_changes(tmp_path, fault):
    m = optional_manifest(tmp_path); p = m['reusable_scene_assets']
    if fault == 'unchecked': p['scenes'][0]['reuse_check'] = ''
    if fault == 'missing': p['scenes'].pop()
    if fault == 'video': p['scenes'][0]['scene_number'] = 4
    if fault == 'forced_assets': p['scenes'][2]['background'] = 'room'
    with pytest.raises(ValueError):
        validate_plan(p, m['scene_specs'], m['character_references'], m['scene_cast'])


def test_new_package_checks_all_stills_and_records_optional_decisions(tmp_path):
    from worker.reusable_scene_assets import plan_package, POLICY
    m = optional_manifest(tmp_path)
    package = {'structure': {'scenes': copy.deepcopy(m['scene_specs']), 'scene_cast': m['scene_cast'],
                            'character_anchors': {'main_character': m['character_references'][0]}},
               'content_setting': {'image_style': 'period illustration'}}
    seen = []
    def stage(job_id, name, context, task):
        seen.append(context)
        return m['reusable_scene_assets']
    plan_package(stage, 'new-job', package)
    assert [s['scene_number'] for s in seen[0]['scenes']] == [1, 2, 3]
    structure = package['structure']
    assert structure['layer_production_stage'] == 'post_submission'
    assert structure['image_generation_policy']['reuse_policy'] == POLICY
    assert structure['image_generation_policy']['shared_composite_scene_numbers'] == [1, 2]
    assert 'image_generation_policy' not in structure['scenes'][2]
    assert 'image_generation_policy' not in structure['scenes'][3]


@pytest.mark.parametrize('policy', [None, 'compatible_first_v2', 'compatible_first_v3'])
def test_script_only_workflow_checks_reuse_only_for_new_policy(tmp_path, monkeypatch, policy):
    from worker import codex_local_workflow as workflow, script_guidelines, script_worker_store
    from worker import elevenlabs_performance, codex_content_runner
    m = optional_manifest(tmp_path)
    package = {'script': 'Saved final narration',
               'structure': {'scenes': copy.deepcopy(m['scene_specs']), 'scene_cast': m['scene_cast'],
                             'character_anchors': {'main_character': m['character_references'][0]}}}
    monkeypatch.setattr(workflow, '_produce', lambda *args: copy.deepcopy(package))
    monkeypatch.setattr(script_worker_store, 'ScriptStore', lambda: object())
    monkeypatch.setattr(script_guidelines, 'approved_guidelines', lambda *args: ([], ''))
    monkeypatch.setattr(elevenlabs_performance, 'annotate_new_package', lambda p, *args: p)
    calls = []
    def stage(self, job_id, name, context, task):
        calls.append(context)
        return m['reusable_scene_assets']
    monkeypatch.setattr(codex_content_runner.CodexStagedContentRunner, '_stage', stage)
    result = workflow.produce('job', {'mode': 'new', 'reuse_check_policy': policy}, None, tmp_path, lambda s: None)
    assert bool(calls) == bool(policy)
    assert result['script'] == package['script']
    assert ('reusable_scene_assets' in result['structure']) == bool(policy)
    if policy == 'compatible_first_v3':
        assert result['structure']['image_request_policy'] == 'reuse_excluded_v1'
        assert result['structure']['reusable_scene_assets']['generation_optimization']['estimated_image_calls'] == 1


def test_cost_gate_keeps_beneficial_reuse_and_discards_expensive_components(tmp_path):
    from worker.reusable_scene_assets import optimize_plan
    m = optional_manifest(tmp_path); p = m['reusable_scene_assets']
    p['scenes'] = [{'scene_number': n, 'mode': 'compose', 'reuse_check': 'Compatible room and pose',
                    'background': 'room', 'poses': ['standing']} for n in range(1, 11)]
    p['scenes'] += [{'scene_number': n, 'mode': 'compose', 'reuse_check': 'Dedicated street shot',
                     'background': 'street', 'poses': []} for n in range(11, 14)]
    # Add a dedicated new pose to make this second group costlier than one flat grid.
    p['poses'].append({'id': 'unique', 'character_key': 'a', 'prompt': 'new street action'})
    for row in p['scenes'][10:]: row['poses'] = ['unique']
    snapshot = copy.deepcopy(p)
    result = optimize_plan(p)
    assert p == snapshot  # Saved inputs are never rewritten.
    assert len([r for r in result['scenes'] if r['mode'] == 'compose']) == 10
    assert all(r['mode'] == 'standalone' for r in result['scenes'][10:])
    assert [a['id'] for a in result['backgrounds']] == ['room']
    assert [a['id'] for a in result['poses']] == ['standing']
    report = result['generation_optimization']
    assert report['baseline_image_calls'] == 4
    assert report['estimated_image_calls'] == 3
    assert report['estimated_calls_saved'] == 1


def test_no_reuse_when_shared_assets_cost_same_or_more_than_flat_grid(tmp_path):
    from worker.reusable_scene_assets import optimize_plan
    m = optional_manifest(tmp_path, standalone=False)
    result = optimize_plan(m['reusable_scene_assets'])
    assert all(r['mode'] == 'standalone' for r in result['scenes'])
    assert result['backgrounds'] == result['poses'] == []
    assert result['generation_optimization']['estimated_image_calls'] == 1
    assert result['generation_optimization']['estimated_calls_saved'] == 0


def optimized_manifest(tmp_path, *, count=10, reuse=(1, 2, 3, 4, 5, 6)):
    from worker.reusable_scene_assets import REQUEST_POLICY
    m = optional_manifest(tmp_path)
    m['image_request_policy'] = REQUEST_POLICY
    m['scene_specs'] = [{'scene_number': n, 'visual_type': 'image', 'image_prompt': f'UNIQUE_SHOT_{n:03d}'}
                        for n in range(1, count + 1)]
    m['scene_specs'].append({'scene_number': count + 1, 'visual_type': 'video', 'image_prompt': 'UPLOADED_VIDEO'})
    m['scene_cast'] = [{'scene_number': n, 'characters': ['A']} for n in range(1, count + 2)]
    m['grids'] = [{'grid_number': i + 1, 'scene_numbers': list(range(n, min(n + 4, count + 1))),
                   'prompt': 'ARCHIVED_GRID_MUST_NOT_BE_SENT', 'raw_file': f'old-{i}.png'}
                  for i, n in enumerate(range(1, count + 1, 4))]
    for g in m['grids']:
        g['scene_numbers'] += [g['scene_numbers'][-1]] * (4 - len(g['scene_numbers']))
    m['reusable_scene_assets']['scenes'] = [
        ({'scene_number': n, 'mode': 'compose', 'reuse_check': 'Compatible pose and room',
          'background': 'room', 'poses': ['standing']} if n in reuse else
         {'scene_number': n, 'mode': 'standalone', 'reuse_check': 'Unique shot'})
        for n in range(1, count + 1)]
    return m


def test_optimized_queue_rebatches_only_new_stills_and_leaves_old_manifests_unchanged(tmp_path):
    from worker import image_recovery as recovery
    m = optimized_manifest(tmp_path)
    original = copy.deepcopy(m)
    jobs = recovery.initialize(m)['jobs']
    assert m == original
    assert len(jobs) == 1 and jobs[0]['scene_numbers'] == [7, 8, 9, 10]
    assert all(f'UNIQUE_SHOT_{n:03d}' not in jobs[0]['prompt'] for n in range(1, 7))
    assert 'UPLOADED_VIDEO' not in jobs[0]['prompt']
    assert 'ARCHIVED_GRID' not in jobs[0]['prompt']
    for n in range(7, 11): assert f'UNIQUE_SHOT_{n:03d}' in jobs[0]['prompt']
    m.pop('image_request_policy')
    assert recovery.initialize(m)['jobs'][0]['id'].startswith('grid-')
    assert all(j['prompt'] == 'ARCHIVED_GRID_MUST_NOT_BE_SENT' for j in recovery.initialize(m)['jobs'])


@pytest.mark.parametrize('remaining', [1, 2, 3, 4, 5])
def test_optimized_tail_mapping_and_quality_split_never_reintroduce_reused_scenes(tmp_path, remaining):
    from worker import image_recovery as recovery
    m = optimized_manifest(tmp_path, count=6 + remaining)
    state = recovery.initialize(m)
    assert len(state['jobs']) == (remaining + 3) // 4
    assert {n for j in state['jobs'] for n in j['scene_numbers']} == set(range(7, 7 + remaining))
    if remaining == 1: assert state['jobs'][0]['layout'] == 'single'
    if remaining in (2, 3):
        job = state['jobs'][0]['id']
        state = recovery.transition(state, {'action': 'start', 'job_id': job})
        state = recovery.transition(state, {'action': 'result', 'job_id': job, 'outcome': 'quality'})
        state = recovery.transition(state, {'action': 'split_quality', 'job_id': job})
        active = [j for j in state['jobs'] if j['status'] != 'superseded']
        assert len(active) == remaining
        assert [n for j in active for n in j['scene_numbers']] == list(range(7, 7 + remaining))


def test_optimized_export_crop_resume_publish_only_requested_images(tmp_path, monkeypatch):
    from worker import cowork_scene_assets as assets, reusable_scene_assets as shared
    from worker import image_recovery as recovery, generated_speaker_coordinates as coordinates
    monkeypatch.syspath_prepend(str(Path(assets.__file__).parent))
    m = optimized_manifest(tmp_path, count=13, reuse=tuple(range(1, 11)))
    m['grids'][-1]['scene_numbers'][-1] = 14  # Archived source plan also covers uploaded video.
    plan = shared.optimize_plan(m['reusable_scene_assets'])
    structure = {'scenes': copy.deepcopy(m['scene_specs']), 'scene_cast': m['scene_cast'],
                 'reusable_scene_assets': plan, 'layer_production_stage': 'post_submission',
                 'image_request_policy': shared.REQUEST_POLICY,
                 'image_grid_prompts': m['grids'],
                 'character_anchors': {'main_character': {'name': 'A', 'character_key': 'a',
                                      'image_url': '/ref.png', 'gcs_path': 'ref.png'}}}
    before = copy.deepcopy(structure)
    monkeypatch.setattr(assets, '_topic', lambda _: ({'id': 1}, structure, 'https://test', {}))
    monkeypatch.setattr(assets, '_download_gcs_bytes', lambda *args: Path(m['character_references'][0]['local_file']).read_bytes())
    path = tmp_path/'export'/'manifest.json'
    assets.export_manifest('1', path, 'scene-bucket')
    exported = json.loads(path.read_text())
    assert structure == before
    assert len(exported['image_requests']) == 1
    assert set(exported['image_requests'][0]['scene_numbers']) == {11, 12, 13}
    grid = tmp_path/'only-new-grid.png'; Image.new('RGB', (800, 800), 'blue').save(grid)
    state_path = recovery.state_path(path); state = json.loads(state_path.read_text())
    for event in ({'action': 'start'}, {'action': 'result', 'outcome': 'generated', 'image_file': str(grid)},
                  {'action': 'accept', 'visual_review': 'Synthetic optimized fixture only'}):
        state = recovery.transition(state, {'job_id': 'flat-001', **event})
    state_path.write_text(json.dumps(state))
    generator = FakeGenerator(tmp_path); original = shared.generate
    monkeypatch.setattr(shared, 'generate', lambda m, d: original(m, d, generator=generator))
    out = tmp_path/'out'; assets.crop_grids(path, tmp_path/'absent', out)
    assert len(list(out.glob('scene-*.png'))) == 13
    assert not (out/'scene-014.png').exists()
    assert len(generator.roles) + len(state['jobs']) == plan['generation_optimization']['estimated_image_calls'] == 3
    pixels = {p.name: p.read_bytes() for p in out.glob('scene-*.png')}
    assets.crop_grids(path, tmp_path/'absent', out)
    assert len(generator.roles) == 2
    assert {p.name: p.read_bytes() for p in out.glob('scene-*.png')} == pixels
    monkeypatch.setattr(assets, '_upload_gcs_file', lambda local, obj, typ: ('scene-bucket', obj, '/asset/'+obj))
    monkeypatch.setattr(coordinates, 'analyze_published_scenes', lambda *args: None)
    saved = []
    monkeypatch.setattr(assets, '_patch_topic_scene_assets', lambda topic, updates, base, headers: saved.extend(updates))
    assert len(assets.publish(path, out, False)) == 13
    assert [r['scene_number'] for r in saved] == list(range(1, 14))
    assert not list(out.glob('*-planes.json'))
