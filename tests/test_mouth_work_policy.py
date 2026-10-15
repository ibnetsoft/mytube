import sys
from pathlib import Path
import pytest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'worker'))
from mouth_work_policy import DEFAULT, normalize, selected_scenes

def story():
    return {'scenes': [{'scene_number': n} for n in range(1, 61)],
        'dialogue_annotations': {'scenes': [{'scene_number': n, 'spans': [
            {'text': 'hello', 'speaker': 'A', 'status': 'confirmed'}]} for n in range(1, 61) if n % 2 == 0]}}

def test_default_selects_first_ten_dialogue_scenes_from_nineteen():
    assert selected_scenes(story(), DEFAULT) == list(range(20, 40, 2))

def test_disabled_zero_custom_and_duplicate_scenes():
    s = story(); s['dialogue_annotations']['scenes'] *= 2
    assert selected_scenes(s, {**DEFAULT, 'enabled': False}) == []
    assert selected_scenes(s, {**DEFAULT, 'max_dialogue_scenes': 0}) == []
    assert selected_scenes(s, {**DEFAULT, 'start_scene': 31, 'max_dialogue_scenes': 2}) == [32,34]

def test_unconfirmed_or_empty_dialogue_does_not_spend_cap():
    s=story(); s['dialogue_annotations']['scenes'][9]['spans'][0]['status']='needs_review'
    assert selected_scenes(s, DEFAULT)[0] == 22

@pytest.mark.parametrize('value', [{'start_scene': 0}, {'max_dialogue_scenes': -1}, {'enabled': 'false'}, {'start_scene': True}])
def test_rejects_invalid_settings(value):
    with pytest.raises(ValueError): normalize(value)


def test_publication_freezes_scope_across_batches_and_publishes_clips(tmp_path, monkeypatch):
    import generated_speaker_coordinates as geometry
    import mouth_work_policy as policy
    import prepared_mouth_layers, prepared_mouth_preview
    from types import SimpleNamespace
    import copy
    monkeypatch.setattr(policy, 'load_policy', lambda: dict(DEFAULT))
    structure = story()
    calls, writes = [], []
    def analyze(_structure, scene, *args):
        calls.append(scene['scene_number'])
        return {'state':'ready','number':scene['scene_number']}
    monkeypatch.setattr(geometry, 'analyze_scene', analyze)
    monkeypatch.setattr(prepared_mouth_layers, 'prepare_scene', lambda *a, **k: {'state':'ready','keys':['pose']})
    monkeypatch.setattr(prepared_mouth_preview, 'prepare_preview', lambda topic, n, *a: {'state':'ready','gcs_path':f'topics/{topic}/mouth-previews/{n}.mp4'})
    publisher = SimpleNamespace(_scene_asset_snapshot=lambda s: {}, _publish_source_snapshot=lambda *a: {},
        _scene_asset_patch=lambda s: copy.deepcopy(s),
        _patch_topic_scene_assets=lambda topic, rows, *a: writes.extend(rows))
    def batch(numbers):
        return {n:{'scene_number':n,'image_url':f'image-{n}','metadata':{'cowork_image_asset':{'gcs_bucket':'bucket','gcs_path':f'{n}.png'}}} for n in numbers}
    geometry.analyze_published_scenes('topic', structure, batch(range(19,31)), tmp_path, '', {}, publisher)
    monkeypatch.setattr(policy, 'load_policy', lambda: {**DEFAULT,'max_dialogue_scenes':100})
    geometry.analyze_published_scenes('topic', structure, batch(range(31,61)), tmp_path, '', {}, publisher)
    assert calls == list(range(20,40,2))
    results={r['scene_number']:r['asset_patch']['metadata']['cowork_image_asset']['speaker_geometry'] for r in writes}
    assert results[38]['mouth_preview']['gcs_path'].endswith('/38.mp4')
    assert results[40]['state']=='not_required'
    assert results[40]['mouth_work_selection']['scene_numbers']==list(range(20,40,2))


def test_settings_api_roundtrip_and_validation(tmp_path, monkeypatch):
    import mouth_work_policy as policy
    from worker.codex_local_console import app, TOKEN
    from fastapi.testclient import TestClient
    monkeypatch.setattr(policy, 'SETTINGS', tmp_path / 'settings.json')
    client = TestClient(app, base_url='http://127.0.0.1:3003')
    headers={'X-Codex-Local':TOKEN}
    assert client.get('/api/mouth-policy').status_code==401
    assert client.get('/api/mouth-policy',headers=headers).json()==DEFAULT
    changed={'enabled':True,'start_scene':22,'max_dialogue_scenes':3}
    assert client.post('/api/mouth-policy',headers=headers,json=changed).json()==changed
    assert client.get('/api/mouth-policy',headers=headers).json()==changed
    assert client.post('/api/mouth-policy',headers=headers,json={**changed,'max_dialogue_scenes':-1}).status_code==422
    assert client.get('/api/mouth-policy',headers=headers).json()==changed
