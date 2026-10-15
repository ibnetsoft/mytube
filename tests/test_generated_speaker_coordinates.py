import copy
import hashlib
import json
import pathlib
import sys
import pytest
from types import SimpleNamespace

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / 'worker'))
import generated_speaker_coordinates as geometry
import cowork_scene_assets as publisher


@pytest.fixture(autouse=True)
def reference_directory(tmp_path, monkeypatch):
    monkeypatch.setattr(geometry, "REFERENCE_ROOT", tmp_path / "references")


def fixture(tmp_path, number=19):
    image = tmp_path / f'scene-{number:03d}.png'
    from PIL import Image, ImageDraw
    pixels=Image.new('RGB',(1000,1000),'white')
    ImageDraw.Draw(pixels).line([(360,470),(440,470)],fill='black',width=3)
    pixels.save(image)
    scene = {'scene_number': number, 'scene_text': 'Mother said hello.', 'image_url': 'image',
             'metadata': {'cowork_image_asset': {'source': 'cowork_builtin_imagegen', 'gcs_bucket': 'bucket', 'gcs_path': f'{number}.png'}}}
    annotation = {'scene_number': number, 'source_sha256': hashlib.sha256(scene['scene_text'].encode()).hexdigest(),
                  'spans': [{'status': 'confirmed', 'speaker': 'Mother', 'text': 'hello'}]}
    structure = {'main_character': {'name': 'Mother'}, 'scenes': [scene], 'dialogue_annotations': {'scenes': [annotation]}}
    return image, scene, structure


class Runner:
    def __init__(self): self.calls = []
    def _stage(self, identity, stage, context, task):
        self.calls.append(context)
        from test_mouth_geometry import speaker as verified_speaker
        row=verified_speaker();row.update(speaker='Mother',confidence=.98,reason='Visible lips')
        if stage=='03_ae_mouth_geometry_review':
            return {'speakers':[{'speaker':'Mother','passed':True,'reason':'Fixture lip markers match source pixels'}]}
        if stage=='03_ae_mouth_crop_localization':
            l,t,r,b=context['crop_rect_pixels']
            def mapped(p): return [(p[0]*1000-l)/(r-l),(p[1]*1000-t)/(b-t)]
            for key in ('face_box','mouth_box'):
                box=row[key];row[key]=mapped(box[:2])+mapped(box[2:])
            g=row['mouth_geometry'];g['face_outline']=[mapped(p) for p in g['face_outline']]
            g['landmarks']={k:mapped(p) for k,p in g['landmarks'].items()}
            return row
        return {'speakers':[row]}


def test_actual_pixels_and_saved_dialogue_are_analyzed_and_reused(tmp_path):
    image, scene, structure = fixture(tmp_path)
    runner = Runner()
    result = geometry.analyze_scene(structure, scene, image, 'bucket', '19.png', runner=runner)
    assert result['state'] == 'ready'
    assert pathlib.Path(runner.calls[0]['_local_image_paths'][0]).read_bytes() == image.read_bytes()
    assert runner.calls[0]['speakers'] == ['Mother']
    assert geometry.analyze_scene(structure, scene, image, 'bucket', '19.png', result, runner) == result
    assert len(runner.calls) == 3
    image.write_bytes(b'replaced pixels')
    assert geometry.analyze_scene(structure, scene, image, 'bucket', '19.png', result, runner)['fingerprint'] != result['fingerprint']
    assert len(runner.calls) == 4


def test_missing_or_stale_annotations_fail_without_guessing_and_narration_skips(tmp_path):
    image, scene, structure = fixture(tmp_path)
    runner = Runner()
    structure['dialogue_annotations']['scenes'][0]['spans'] = []
    assert geometry.analyze_scene(structure, scene, image, 'bucket', '19.png', runner=runner)['state'] == 'not_required'
    scene['scene_text'] += ' changed'
    assert geometry.analyze_scene(structure, scene, image, 'bucket', '19.png', runner=runner)['state'] == 'needs_review'
    assert not runner.calls


def test_low_confidence_and_missing_face_are_review_not_ready(tmp_path):
    image, scene, structure = fixture(tmp_path)
    for speaker in [{'speaker': 'Mother', 'status': 'uncertain', 'confidence': .5, 'reason': 'Occluded'},
                    {'speaker': 'Mother', 'status': 'visible', 'confidence': .99, 'mouth_box': [.2,.3,.25,.34], 'reason': 'Lips'}]:
        runner = SimpleNamespace(_stage=lambda *args: {'speakers': [speaker]})
        assert geometry.analyze_scene(structure, scene, image, 'bucket', '19.png', runner=runner)['state'] == 'needs_review'


def test_directed_blink_is_verified_against_final_image_and_saved(tmp_path):
    image, scene, structure = fixture(tmp_path)
    scene['scene_direction_plan'] = {'eye_blink_plan': {
        'enabled': True, 'character': 'Mother', 'reason': 'reaction pause',
        'cues': [{'at_seconds': 2.4, 'duration_seconds': .11, 'type': 'single'}],
    }}
    class BlinkRunner(Runner):
        def _stage(self, identity, stage, context, task):
            if stage == '03_ae_eye_visibility':
                return {'eye_blink': {'character': 'Mother', 'status': 'visible', 'confidence': .98,
                    'left_eye_box': [.2,.2,.24,.23], 'right_eye_box': [.3,.2,.34,.23],
                    'reason': 'Both eyes are unobscured on Mother.'}}
            return super()._stage(identity, stage, context, task)
    result = geometry.analyze_scene(structure, scene, image, 'bucket', '19.png', runner=BlinkRunner())
    assert result['state'] == 'ready'
    assert result['eye_blink']['state'] == 'ready'
    assert result['eye_blink']['character'] == 'Mother'
    assert result['eye_blink']['cues'][0]['at_seconds'] == 2.4


def test_each_scene_checkpoint_failure_continues_and_early_video_skips(tmp_path, monkeypatch):
    image, scene, structure = fixture(tmp_path)
    _, scene20, _ = fixture(tmp_path, 20)
    _, early, _ = fixture(tmp_path, 5)
    scenes = {5: early, 19: scene, 20: scene20}
    writes = []
    monkeypatch.setattr(geometry, 'analyze_scene', lambda st, sc, *args: {'state': 'needs_review' if sc['scene_number'] == 19 else 'ready', 'number': sc['scene_number']})
    fake = SimpleNamespace(_scene_asset_snapshot=publisher._scene_asset_snapshot,
        _publish_source_snapshot=publisher._publish_source_snapshot, _scene_asset_patch=publisher._scene_asset_patch,
        _patch_topic_scene_assets=lambda topic, updates, *args: writes.append(copy.deepcopy(updates)))
    geometry.analyze_published_scenes('topic', structure, scenes, tmp_path, '', {}, fake)
    assert [w[0]['scene_number'] for w in writes] == [19, 20]
    assert writes[1][0]['asset_patch']['metadata']['cowork_image_asset']['speaker_geometry']['state'] == 'not_required'
    assert json.loads((tmp_path / 'scene-019-speaker-coordinates.json').read_text())['state'] == 'needs_review'
    assert 'speaker_geometry' not in writes[0][0]['expected_assets']['metadata']['cowork_image_asset']


def test_publish_runs_analysis_after_image_commit(tmp_path, monkeypatch):
    from PIL import Image
    image, scene, structure = fixture(tmp_path)
    Image.new('RGB', (1920,1080)).save(image)
    manifest = tmp_path / 'manifest.json'
    manifest.write_text(json.dumps({'schema':'cowork_scene_assets/v1', 'topic_id': '123', 'bucket':'air-studio-prod','scene_specs':[scene], 'grids':[{'scene_numbers':[19]}]}))
    monkeypatch.setattr(publisher, '_topic', lambda _: ({}, copy.deepcopy(structure), '', {}))
    monkeypatch.setattr(publisher, '_upload_gcs_file', lambda *args: ('bucket','19.png','image'))
    steps = []
    monkeypatch.setattr(publisher, '_patch_topic_scene_assets', lambda *args: steps.append('image committed'))
    # Publisher imports the package module, as in normal CLI invocation.
    import generated_speaker_coordinates as packaged
    monkeypatch.setattr(packaged, 'analyze_published_scenes', lambda *args: steps.append('analyze'))
    publisher.publish(manifest, tmp_path, False)
    assert steps == ['image committed','analyze']


def test_database_conflict_keeps_local_receipt_and_does_not_claim_success(tmp_path, monkeypatch):
    _, scene, structure = fixture(tmp_path)
    monkeypatch.setattr(geometry, 'analyze_scene', lambda *args: {'state':'ready','number':19,'fingerprint':'same'})
    def conflict(*args): raise RuntimeError('asset_conflict')
    fake = SimpleNamespace(_scene_asset_snapshot=publisher._scene_asset_snapshot,
        _publish_source_snapshot=publisher._publish_source_snapshot, _scene_asset_patch=publisher._scene_asset_patch,
        _patch_topic_scene_assets=conflict)
    with pytest.raises(RuntimeError, match='asset_conflict'):
        geometry.analyze_published_scenes('topic', structure, {19:scene}, tmp_path, '', {}, fake)
    assert json.loads((tmp_path / 'scene-019-speaker-coordinates.json').read_text())['state'] == 'ready'
    assert 'speaker_geometry' not in scene['metadata']['cowork_image_asset']


def test_geometry_publication_preserves_queued_layer_state(tmp_path, monkeypatch):
    image, scene, structure = fixture(tmp_path)
    scene['psd_layer_status'] = 'queued'
    scene['metadata']['cowork_image_asset']['source'] = 'codex_builtin_imagegen'
    scene['metadata']['psd_layer_plan'] = {'template': 'pending-user-direction'}
    writes=[]
    monkeypatch.setattr(geometry, 'analyze_scene', lambda *args: {'state':'needs_review','number':19})
    fake=SimpleNamespace(_scene_asset_snapshot=publisher._scene_asset_snapshot,
        _publish_source_snapshot=publisher._publish_source_snapshot,
        _patch_topic_scene_assets=lambda topic,updates,*args:writes.extend(copy.deepcopy(updates)))
    geometry.analyze_published_scenes('topic',structure,{19:scene},tmp_path,'',{},fake)
    patch=writes[0]['asset_patch']
    assert writes[0]['expected_assets']['psd_layer_status']=='queued'
    assert 'scene_direction_plan' in writes[0]['expected_source']
    assert 'psd_layer_status' not in patch
    assert 'psd_layer_plan' not in patch['metadata']
    assert patch['metadata']['cowork_image_asset']['source']=='codex_builtin_imagegen'
    assert scene['psd_layer_status']=='queued'
