import copy
import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'worker'))
import ae_mouth as mouth
import ae_mouth_worker as worker
import ae_highlight_worker as ae


def test_semantic_assessment_preserves_saved_dialogue_and_narration():
    rows = [{'index': 2, 'text': '그는 편지를 읽었다.', 'kind': 'narration', 'scene_number': 19}]
    assert mouth.dialogue_rows({'rows': [{'index': 2, 'text': rows[0]['text'], 'kind': 'narration', 'reason': 'reported writing'}]}, rows)[0]['kind'] == 'narration'
    with pytest.raises(ValueError, match='classification'):
        mouth.dialogue_rows({'rows': [{'index': 2, 'text': rows[0]['text'], 'kind': 'dialogue', 'speaker': '소녀', 'reason': 'guess'}]}, rows)


def test_hidden_ambiguous_and_overlapping_mouths_cannot_be_animated():
    known = {'speaker': '소녀', 'status': 'visible', 'confidence': .95, 'mouth_box': [.4, .4, .45, .43], 'reason': 'visible lips'}
    assert mouth.visible_speakers({'speakers': [known]}, ['소녀']) == [known]
    with pytest.raises(ValueError, match='confidence'):
        mouth.visible_speakers({'speakers': [{**known, 'confidence': .4}]}, ['소녀'])
    with pytest.raises(ValueError, match='overlap'):
        mouth.visible_speakers({'speakers': [known, {**known, 'speaker': '어머니'}]}, ['소녀', '어머니'])
    with pytest.raises(ValueError, match='visibility'):
        mouth.visible_speakers({'speakers': [{**known, 'status': 'uncertain'}]}, ['소녀'])


def test_amplitude_animation_stays_closed_during_narration_and_voice_pauses():
    samples = [0] * 8000 + [1000, -1000] * 2000 + [0] * 2000 + [1000, -1000] * 1000 + [0] * 8000
    cues = mouth.amplitude_cues(samples, [{'start': 1, 'end': 2}], start=0, duration=3)
    def pose(t):
        return next(c['pose'] for c in reversed(cues) if c['at_seconds'] <= t)
    assert pose(.5) == 'closed'
    assert pose(1.2) in ('open', 'half')
    assert pose(1.6) == 'closed'
    assert pose(2.5) == 'closed'
    assert cues[-1]['pose'] == 'closed'
    with pytest.raises(ValueError, match='boundary'):
        mouth.amplitude_cues(samples, [{'start': 2, 'end': 4}], start=0, duration=3)


def test_ae_source_precomp_keeps_lips_attached_to_existing_camera_and_effects(tmp_path):
    scene = {'ae_motion_plan': {'enabled': True}, 'ae_mouth_runtime': {'enabled': True, 'speakers': [
        {'mouth_box': [.4, .4, .45, .43], 'layers': {p: str(tmp_path / f'{p}.png') for p in mouth.POSES},
         'cues': [{'at_seconds': 0, 'pose': 'closed'}, {'at_seconds': 1, 'pose': 'open'}]}]}}
    job = ae.SceneJob('p', 'title', {'scenes': [scene]}, 0, scene, 19, 'motion', 'subtle', 18, ae.GcsRef('__local__', 'original.png'))
    path = tmp_path / 'create.jsx'
    ae._write_jsx(job, tmp_path / 'original.png', tmp_path / 'project.aep', tmp_path / 'render.mp4', path)
    text = path.read_text(encoding='utf-8')
    assert 'var DUR = 18.000' in text
    assert text.index('footage = mouthComp') < text.index('bg = comp.layers.add(footage)')
    assert '&& !mouthRuntime.enabled' in text
    assert 'KeyframeInterpolationType.HOLD' in text


def test_snapshot_invalidates_new_sources_but_ignores_generated_output():
    project = {'project_payload': {'subtitles': [{'text': 'hello', 'scene_number': 19, 'start': 0, 'end': 1, 'voice_id': 'girl'}]}}
    assets = [{'id': 'audio', 'asset_type': 'audio', 'status': 'uploaded', 'metadata': {}},
              {'id': 'image', 'asset_type': 'image', 'status': 'uploaded', 'scene_number': 19, 'metadata': {}}]
    scenes = [{'scene_number': 19, 'scene_text': 'hello'}]
    snapshot = {'audio': {'id': 'audio', 'metadata': {}}, 'cast': {'main': {}, 'supporting': [], 'scene_cast': []}, 'annotations': {},
                'subtitles': [{'index': 0, 'text': 'hello', 'scene_number': 19, 'start': 0, 'end': 1, 'voice_id': 'girl', 'kind': '', 'speaker': ''}],
                'scenes': [{'number': 19, 'text': 'hello', 'image': {'id': 'image', 'metadata': {}},
                            'direction': {'ae_motion_plan': None, 'ae_effect_plan': None, 'ae_directorial_plan': None, 'image_prompt': ''}}]}
    assert worker.input_matches(snapshot, project, assets, scenes)
    assert worker.input_matches(snapshot, project, [{'id': 'output', 'asset_type': 'video', 'status': 'uploaded'}, *assets], scenes)
    changed = copy.deepcopy(assets); changed[0]['id'] = 'new-audio'
    assert not worker.input_matches(snapshot, project, changed, scenes)
    changed = copy.deepcopy(project); changed['project_payload']['subtitles'][0]['direction'] = 'whisper'
    assert not worker.input_matches(snapshot, changed, assets, scenes)


def test_submitted_job_discovers_then_waits_for_direction_approval_before_generating(monkeypatch, tmp_path):
    import json
    from PIL import Image, ImageDraw
    from lipsync_video_worker import ffmpeg, run
    master, original = tmp_path / 'voice.wav', tmp_path / 'original.png'
    run([ffmpeg(), '-y', '-f', 'lavfi', '-i', 'sine=frequency=220:duration=19', '-ac', '1', str(master)])
    Image.new('RGB', (1280, 720), '#d6b8a1').save(original)
    subtitles = [{'index': 0, 'text': 'hello', 'scene_number': 19, 'start': 1, 'end': 2, 'voice_id': 'girl', 'kind': 'dialogue', 'speaker': 'girl'},
                 {'index': 1, 'text': 'ending', 'scene_number': 20, 'start': 18, 'end': 19, 'voice_id': 'n', 'kind': 'narration', 'speaker': ''}]
    saved = [{**r, 'dialogue_kind': r['kind'], 'dialogue_speaker': r['speaker']} for r in subtitles]
    project = {'id': 'p', 'project_payload': {'subtitles': saved}}
    scenes = [{'scene_number': n, 'scene_text': text} for n, text in [(19, 'hello'), (20, 'ending')]]
    audio_meta = {'gcs_bucket': 'bucket', 'gcs_path': 'voice.wav'}
    assets = [{'id': 'audio', 'asset_type': 'audio', 'status': 'uploaded', 'metadata': audio_meta},
              *[{'id': f'image{n}', 'asset_type': 'image', 'status': 'uploaded', 'scene_number': n,
                 'metadata': {'gcs_bucket': 'bucket', 'gcs_path': f'image{n}.png'}} for n in (19, 20)]]
    snapshot = {'project_id': 'p', 'audio': {'id': 'audio', 'metadata': audio_meta}, 'subtitles': subtitles,
                'cast': {'main': {}, 'supporting': [], 'scene_cast': []}, 'annotations': {}, 'scenes': [
                    {'number': n, 'text': text, 'start': start, 'end': end, 'image': {'id': f'image{n}', 'metadata': assets[i+1]['metadata']},
                     'direction': {'ae_motion_plan': None, 'ae_effect_plan': None, 'ae_directorial_plan': None, 'image_prompt': ''}}
                    for i, (n, text, start, end) in enumerate([(19, 'hello', 0, 18), (20, 'ending', 18, 19)])]}
    snapshot['scenes'][0]['speaker_regions'] = {'image_id':'image19','source_sha256':mouth.digest(original),
        'speakers':[{'speaker':'girl','status':'visible','confidence':.98,'face_box':[.2,.2,.7,.7], 'mouth_box':[.4,.4,.48,.44],'reason':'saved original-image geometry'}]}
    job = {'id': 'job', 'project_id': 'p', 'asset_type': 'other', 'updated_at': 'initial',
           'metadata': {'kind': 'ae_mouth_job', 'state': 'queued', 'fingerprint': 'test-fingerprint', 'input': snapshot, 'results': []}}
    class Response:
        def __init__(self, value): self.value = copy.deepcopy(value)
        def json(self): return self.value
    def request(method, url, headers, params=None, json=None):
        params = params or {}
        if method == 'GET':
            if url.endswith('std_projects'): return Response([project])
            if url.endswith('std_project_scenes'): return Response(scenes)
            if 'metadata->>kind' in params:
                return Response([job] if job['metadata']['state'] in ('queued', 'processing', 'direction_approved') else [])
            if 'metadata->>ae_mouth_fingerprint' in params:
                return Response([a for a in assets if a.get('metadata', {}).get('ae_mouth_fingerprint')])
            return Response([job, *assets])
        if method == 'PATCH':
            job.update(copy.deepcopy(json)); return Response([job])
        if method == 'POST':
            asset = {**json, 'id': 'output'}; assets.insert(0, asset); return Response([asset])
        raise AssertionError(method)
    monkeypatch.setattr(worker, 'ROOT', tmp_path)
    monkeypatch.setattr(ae, '_supabase', lambda: ('https://db', {}))
    monkeypatch.setattr(ae, '_request', request)
    def download(ref, target):
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((master if 'voice' in ref.path else original).read_bytes())
    monkeypatch.setattr(ae, '_download_gcs_file', download)
    monkeypatch.setattr(ae, '_upload_gcs_file', lambda p, name, mime: ('bucket', name, '/preview'))
    generated = []
    class Generator:
        def generate(self, *, role, prompt, reference, work_dir):
            generated.append(prompt); work_dir.mkdir(parents=True, exist_ok=True)
            path = work_dir / 'source.png'; image = Image.new('RGB', (512, 512), '#d6b8a1')
            if 'naturally open' in prompt: ImageDraw.Draw(image).ellipse((80, 100, 430, 400), fill='#442222')
            elif 'slightly parted' in prompt: ImageDraw.Draw(image).ellipse((80, 220, 430, 300), fill='#442222')
            else: ImageDraw.Draw(image).line((80, 255, 430, 255), fill='#442222', width=8)
            image.save(path); return path
    class Runner:
        def _stage(self, identity, name, context, task):
            if 'dialogue' in name:
                return {'rows': [{**r, 'reason': 'actual speech' if r['kind'] == 'dialogue' else 'narration'} for r in subtitles]}
            if 'visibility' in name or 'dialogue' in name:
                raise AssertionError('Submitted AE must use saved dialogue and geometry')
            return {'passed': True, 'reason': 'clean three-pose overlays'}
    monkeypatch.setattr(worker, 'CodexStagedContentRunner', Runner)
    monkeypatch.setattr(worker, 'NativeCodexLayerGenerator', Generator)
    def render(spec, keep_workdir):
        assert spec.duration_seconds == 18  # No old twelve-second AE cap.
        assert spec.scene['ae_mouth_runtime']['enabled']
        output = tmp_path / 'ae.mp4'
        run([ffmpeg(), '-y', '-f', 'lavfi', '-i', 'color=c=tan:s=32x32:r=24:d=18', '-c:v', 'libx264', str(output)])
        return {'local_path': str(output)}
    monkeypatch.setattr(ae, '_render_job', render)
    assert worker.process_one()
    assert job['metadata']['state'] == 'direction_pending'
    assert generated == []
    assert [r['status'] for r in job['metadata']['results']] == ['direction_pending', 'skipped']
    job['metadata']['state'] = 'direction_approved'; job['metadata']['phase'] = 'render'
    job['metadata']['results'][0]['status'] = 'direction_approved'
    assert worker.process_one()
    assert job['metadata']['state'] == 'review_pending'
    assert len(generated) == 3
    assert [r['status'] for r in job['metadata']['results']] == ['review_pending', 'skipped']
    output = next(a for a in assets if a['asset_type'] == 'video')
    assert output['metadata']['timing_locked'] is True
    assert output['metadata']['ae_reviewed'] is False
