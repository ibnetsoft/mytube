import hashlib
import json
import subprocess
from pathlib import Path

import pytest
from PIL import Image

from scripts import finish_user_topic_images as producer


def test_grid_generation_reuses_actual_output_with_same_references(tmp_path, monkeypatch):
    monkeypatch.setattr(producer, 'ART', tmp_path / 'art')
    reference = tmp_path / 'reference.png'
    Image.new('RGB', (512, 512), 'blue').save(reference)
    ref_hash = hashlib.sha256(reference.read_bytes()).hexdigest()
    calls = []
    def fake_run(command, *, cwd, **kwargs):
        calls.append(command)
        Image.new('RGB', (1024, 1024), 'white').save(Path(cwd) / 'source.png')
        (Path(cwd) / 'response.json').write_text(json.dumps({'status': 'ready', 'image_file': 'source.png'}), encoding='utf8')
        return subprocess.CompletedProcess(command, 0, stdout='', stderr='')
    monkeypatch.setattr(producer.subprocess, 'run', fake_run)
    job = {'id': 'grid-001', 'prompt': 'four scenes', 'references': [
        {'character_key': 'lead', 'name': 'Lead', 'local_file': str(reference), 'sha256': ref_hash}]}
    first = producer.grid(job)
    assert producer.grid(job) == first
    assert len(calls) == 1 and 'referenced_image_paths' in calls[0][-1]
    Image.new('RGB', (512, 512), 'red').save(reference)
    with pytest.raises(ValueError, match='changed character reference'):
        producer.grid(job)


def test_scene_state_source_request_preserves_unconfirmed_timing(tmp_path, monkeypatch):
    from worker import character_states
    images = tmp_path / 'images'
    images.mkdir()
    base = images / 'scene-019-background.png'
    Image.new('RGB', (1920, 1080), 'white').save(base)
    sha = hashlib.sha256(base.read_bytes()).hexdigest()
    (images / 'scene-019-planes.json').write_text(json.dumps({'files': {'background': sha}}), encoding='utf8')
    manifest = {'scene_specs': [{'scene_number': 19, 'scene_direction_plan': {
        'scene_state_request': {'count': 3, 'scene_text': 'A room at dusk'}}}]}
    def fake_prepare(plan, files, request, runner, generator, directory):
        return {**plan, 'scene_state_plan': {'status': 'unchanged', 'reason': 'No change in the script'}}, files, []
    monkeypatch.setattr(character_states, 'prepare_scene_states', fake_prepare)
    results = producer.prepare_requested_scene_states(manifest, images, '42')
    assert results[0]['scene_number'] == 19
    assert results[0]['plan']['status'] == 'unchanged'
    assert results[0]['plan']['timing_status'] == 'unconfirmed'


def test_face_sources_have_unconfirmed_timing_and_no_identity_review(tmp_path, monkeypatch):
    from worker import manga_layer_generation as layers
    images = tmp_path / 'images'
    images.mkdir()
    source = images / 'scene-019-character-01.png'
    Image.new('RGBA', (1920,1080), (0,0,0,0)).save(source)
    (images / 'scene-019-planes.json').write_text(json.dumps({'character_keys': {'character-01': 'lead'}}), encoding='utf8')
    class Fake:
        def generate(self, **kwargs):
            work = kwargs['work_dir']; work.mkdir(parents=True, exist_ok=True)
            out = work / 'generated.png'
            image = Image.new('RGBA',(512,512),(0,0,0,0))
            image.paste((200,80,40,255),(100,100,300,400))
            image.save(out)
            return out
    monkeypatch.setattr(layers, 'NativeCodexLayerGenerator', Fake)
    manifest = {'mouth_work_selection': {'scene_numbers': [19]},
        'scene_specs':[{'scene_number':19,'scene_direction_plan':{'eye_blink_plan':{'enabled':True,'character':'A'}}}],
        'scene_cast':[{'scene_number':19,'characters':['A']}],
        'character_references':[{'name':'A','character_key':'lead'}]}
    structure = {'dialogue_annotations':{'scenes':[{'scene_number':19,'spans':[{'speaker':'A','status':'confirmed','text':'yes'}]}]}}
    results, unresolved = producer.prepare_face_motion_sources(manifest, images, structure)
    assert not unresolved and len(results) == 1
    assert set(results[0]['poses_sha256']) == {'mouth_closed','mouth_half','mouth_open','eyes_closed'}
    assert results[0]['timing_status'] == 'unconfirmed'
    assert results[0]['identity_review'] == 'not_requested'
