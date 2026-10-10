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


def test_audio_reactive_light_is_bounded_and_dialogue_only():
    samples = [0] * 8000 + [1200, -1200] * 4000 + [1200, -1200] * 4000
    cues = mouth.audio_reactive_light_cues(samples, [{'start': 1, 'end': 2}], start=0, duration=3)
    def level(t):
        return next(c['value'] for c in reversed(cues) if c['at_seconds'] <= t)
    assert level(.5) == 0
    assert 0 < level(1.5) <= 1
    assert level(2.5) == 0
    assert cues[-1] == {'at_seconds': 3, 'value': 0.0}


def test_user_selected_eye_blink_is_brief_bounded_and_composited_inside_source():
    cues = mouth.blink_cues(10, 4)
    assert cues[0] == {'at_seconds': 0, 'opacity': 0}
    assert cues[-1] == {'at_seconds': 10, 'opacity': 0}
    assert any(c['opacity'] == 100 for c in cues)
    assert all(0 <= c['at_seconds'] <= 10 and c['opacity'] in (0, 100) for c in cues)
    jsx = mouth.mouth_jsx({'enabled': True, 'speakers': [], 'blinks': [{
        'left_eye_box': [.2,.2,.24,.23], 'right_eye_box': [.3,.2,.34,.23],
        'layers': {'left':'left.png','right':'right.png'}, 'cues': cues,
    }]})
    assert 'blink_' in jsx
    assert 'runtimeBlinks' in jsx
    assert jsx.index('var runtimeBlinks') < jsx.index('footage = mouthComp')


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
    assert 'audio_reactive_dialogue_light' in text
    assert 'Math.min(4, lightCue.value * 4)' in text


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


def test_snapshot_requires_the_same_confirmed_eye_plan():
    project = {'project_payload': {'subtitles': [{'text':'still','scene_number':19,'start':0,'end':1,'voice_id':'n'}]}}
    image = {'id':'image','asset_type':'image','status':'uploaded','scene_number':19,'metadata':{}}
    audio = {'id':'audio','asset_type':'audio','status':'uploaded','metadata':{}}
    blink_meta = {'kind':'eye_blink_confirmation','state':'confirmed','version':1,'image_id':'image','source_sha256':'a'*64,
                  'character':'girl','left_eye_box':[.2,.2,.24,.23],'right_eye_box':[.3,.2,.34,.23],'interval_seconds':4}
    blink = {'id':'blink','asset_type':'other','status':'uploaded','scene_number':19,'metadata':blink_meta}
    plan = {'id':'blink','version':1,'character':'girl','image_id':'image','source_sha256':'a'*64,
            'left_eye_box':[.2,.2,.24,.23],'right_eye_box':[.3,.2,.34,.23],'interval_seconds':4}
    snapshot = {'audio':{'id':'audio','metadata':{}},'cast':{'main':{},'supporting':[],'scene_cast':[]},'annotations':{},
                'subtitles':[{'index':0,'text':'still','scene_number':19,'start':0,'end':1,'voice_id':'n','kind':'','speaker':'','direction':''}],
                'scenes':[{'number':19,'text':'still','image':{'id':'image','metadata':{}},'original_video':None,'eye_blink':plan,
                           'direction':{'ae_motion_plan':None,'ae_effect_plan':None,'ae_directorial_plan':None,'image_prompt':''}}]}
    scenes = [{'scene_number':19,'scene_text':'still'}]
    assert worker.input_matches(snapshot,project,[blink,image,audio],scenes)
    changed=copy.deepcopy(blink);changed['id']='blink2';changed['metadata']['interval_seconds']=6
    assert not worker.input_matches(snapshot,project,[changed,image,audio],scenes)


@pytest.mark.parametrize('video_scene,auto_video', [(False,False),(True,False),(True,True)])
def test_submitted_job_discovers_then_waits_for_direction_approval_before_generating(monkeypatch, tmp_path, video_scene, auto_video):
    import json
    from PIL import Image, ImageDraw
    from ae_media_utils import ffmpeg, run
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
    tracked = []
    if video_scene:
        snapshot['version'] = 2
        snapshot['scenes'][0]['number'] = 12
        snapshot['subtitles'][0]['scene_number'] = 12
        saved[0]['scene_number'] = 12
        scenes[0]['scene_number'] = 12
        assets[1]['scene_number'] = 12
        video = {'id': 'video12', 'asset_type': 'video', 'status': 'uploaded', 'scene_number': 12,
                 'metadata': {'gcs_bucket': 'bucket', 'gcs_path': 'video12.mp4'}}
        assets.append(video)
        snapshot['scenes'][0]['original_video'] = {'id': video['id'], 'metadata': video['metadata']}
        # Scene 5 has dialogue and a video, but no coordinates. It must not block scene 12.
        missing = copy.deepcopy(snapshot['scenes'][0])
        missing.update(number=5, speaker_regions=None)
        missing['image'] = {**missing['image'], 'id': 'image5'}
        missing['original_video'] = {**missing['original_video'], 'id': 'video5'}
        snapshot['scenes'].insert(0, missing)
        row = {**subtitles[0], 'index': 2, 'scene_number': 5}
        subtitles.append(row); saved.append({**row, 'dialogue_kind': 'dialogue', 'dialogue_speaker': 'girl'})
        scenes.insert(0, {'scene_number': 5, 'scene_text': 'hello'})
        assets.extend([{**assets[1], 'id': 'image5', 'scene_number': 5}, {**video, 'id': 'video5', 'scene_number': 5}])
        # The first-frame reference is an 'other' asset, not an editor image replacement.
        assets[1]['asset_type'] = 'other'
        assets[1]['metadata'] = {**assets[1]['metadata'], 'kind': 'speaker_video_reference',
            'source_video_id': 'video12', 'source_video_path': 'video12.mp4',
            'source_video_sha256': mouth.digest(original)}
        snapshot['scenes'][1]['image']['metadata'] = assets[1]['metadata']
        def track(video, image, speakers, directory, duration):
            tracked.append(duration)
            return image, speakers, {'source_duration': 3, 'speakers': speakers}
        monkeypatch.setattr(worker, 'track_video', track)
    job = {'id': 'job', 'project_id': 'p', 'asset_type': 'other', 'updated_at': 'initial',
           'metadata': {'kind': 'ae_mouth_job', 'state': 'queued', 'fingerprint': 'test-fingerprint', 'input': snapshot, 'results': [], 'auto_video_coordinates': auto_video}}
    class Response:
        def __init__(self, value): self.value = copy.deepcopy(value)
        def json(self): return self.value
    def request(method, url, headers, params=None, json=None):
        params = params or {}
        if method == 'GET':
            if url.endswith('std_projects'): return Response([project])
            if url.endswith('std_project_scenes'): return Response(scenes)
            if 'metadata->>kind' in params:
                assert 'updated_at.lt.' in params['or']
                return Response([job] if job['metadata']['state'] in ('queued', 'processing', 'direction_approved') else [])
            if 'metadata->>ae_mouth_fingerprint' in params:
                return Response([a for a in assets if a.get('metadata', {}).get('ae_mouth_fingerprint')])
            return Response([job, *assets])
        if method == 'PATCH':
            if 'updated_at' not in params:
                assert params['metadata->>worker_token'] == 'eq.' + job['metadata']['worker_token']
            job.update(copy.deepcopy(json)); return Response([job])
        if method == 'POST':
            asset = {**json, 'id': 'output'}; assets.insert(0, asset); return Response([asset])
        raise AssertionError(method)
    if auto_video:
        def prepare(runner, project_id, scene, dialogue, cast, directory, fresh, allow_analyze):
            fresh()
            if scene['number'] == 5:
                raise ValueError('face is obscured')
            tracked.append(scene['end']-scene['start'])
            path = directory / 'original-video.mp4'
            path.write_bytes(original.read_bytes())
            visibility = copy.deepcopy(scene['speaker_regions']['speakers'])
            return path, original, visibility, copy.deepcopy(visibility), {'source_duration':3}, 'saved-video-coordinates'
        monkeypatch.setattr(worker, 'prepare_submitted_video', prepare)
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
        assert spec.scene['ae_mouth_runtime']['video_source'] is video_scene
        if video_scene:
            assert spec.scene_number == 12
            assert spec.source.path.endswith('original-video.mp4')
        output = tmp_path / 'ae.mp4'
        run([ffmpeg(), '-y', '-f', 'lavfi', '-i', 'color=c=tan:s=32x32:r=24:d=18', '-c:v', 'libx264', str(output)])
        return {'local_path': str(output)}
    monkeypatch.setattr(ae, '_render_job', render)
    if video_scene:
        assert worker.process_one(should_stop=lambda: any(r.get('number') == 5 for r in job['metadata']['results']))
        assert job['metadata']['state'] == 'processing'
        assert tracked == []
        assert next(r for r in job['metadata']['results'] if r['number'] == 5)['status'] == ('needs_review' if auto_video else 'skipped')
    assert worker.process_one()
    assert job['metadata']['state'] == 'direction_pending'
    assert generated == []
    assert [r['status'] for r in job['metadata']['results']] == ([('needs_review' if auto_video else 'skipped'), 'direction_pending', 'skipped'] if video_scene else ['direction_pending', 'skipped'])
    if video_scene:
        if auto_video:
            assert job['metadata']['results'][0]['coordinate_state'] == 'needs_review'
            assert job['metadata']['results'][1]['video_coordinate_asset_id'] == 'saved-video-coordinates'
        else:
            assert job['metadata']['results'][0]['skip_reason'] == 'missing_speaker_coordinates'
        assert tracked == [18]
    job['metadata']['state'] = 'direction_approved'; job['metadata']['phase'] = 'render'
    job['metadata']['results'][1 if video_scene else 0]['status'] = 'direction_approved'
    assert worker.process_one()
    assert job['metadata']['state'] == 'review_pending'
    assert len(generated) == 3
    assert [r['status'] for r in job['metadata']['results']] == ([('needs_review' if auto_video else 'skipped'), 'review_pending', 'skipped'] if video_scene else ['review_pending', 'skipped'])
    output = next(a for a in assets if a.get('metadata', {}).get('ae_mouth_fingerprint'))
    assert output['metadata']['source_video_id'] == ('video12' if video_scene else None)
    assert output['metadata']['timing_locked'] is True
    assert output['metadata']['ae_reviewed'] is False
