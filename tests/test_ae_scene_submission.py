import copy
import hashlib
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'worker'))
from submission_pipeline import ready_scene_artifacts, validate_required_scene_results, sequence_fingerprint
from ae_scene_animation import canonical_plan_sha256
from ae_scene_review_contract import (BOUNDARY_CHECKS, RENDER_CHECKS, render_review_matches,
                                      sequence_review_matches, sample_times)


def checks(ids):
    return {'passed': True, 'critical_issues': [], 'checks': [
        {'id': identity, 'passed': True, 'evidence': 'Inspected actual source/output pixels'} for identity in ids]}


def complete_review(scene, audio, checksum):
    result = scene['ae_scene']['metadata']['result']
    times = sample_times(result['plan'], scene['end'] - scene['start'])
    return {'passed': True, 'version': 1, 'method': 'sampled_actual_frames_and_decoded_final_audio',
        'source_sha256': result['source_sha256'], 'plan_sha256': result['plan_sha256'],
        'source_preview_sha256': 'd' * 64, 'render_sha256': checksum,
        'audio': {'source_audio_id': audio['id'], 'final_audio_sha256': 'e' * 64,
            'method': 'decoded_pcm_integrity_not_audio_audition', 'scene_start_seconds': scene['start'],
            'scene_end_seconds': scene['end'], 'sample_rate': 8000, 'correlation': .99, 'rms_ratio': 1.,
            'source_samples': 16000, 'output_samples': 16000},
        'video': {'fps': 24, 'frames': 48, 'duration': 2., 'width': 320, 'height': 180},
        'batches': [{'seconds': times, 'frames': [{'seconds': t, 'sha256': 'f' * 64} for t in times],
                     'review': checks(RENDER_CHECKS)}]}


def complete_sequence(meta):
    checksum = meta['results'][0]['render_sha256']
    return {'passed': True, 'version': 1, 'method': 'sampled_actual_adjacent_frames',
        'ae_scene_numbers': [2], 'checked_boundaries': [{
            'from': 1, 'to': 2, 'review': checks(BOUNDARY_CHECKS), 'evidence': [
                {'number': 1, 'media_sha256': 'f' * 64, 'kind': 'original_image', 'source_asset_id': 'image',
                 'source_storage': {}, 'frames': [{'seconds': 0, 'sha256': 'f' * 64}]},
                {'number': 2, 'media_sha256': checksum, 'kind': 'actual_postprocessed_output',
                 'frames': [{'seconds': 0, 'sha256': 'f' * 64}, {'seconds': 1.9, 'sha256': 'f' * 64}]}]}]}


def fixture():
    plan = {'contract': 'ae_scene/v1', 'schema_version': 'ae_scene/v1', 'timing': 'normalized',
        'width': 320, 'height': 180, 'output': {'width': 320, 'height': 180},
        'camera': [{'t': 0, 'x': .5, 'y': .5, 'scale': 1.1, 'rotation': 0},
                   {'t': 1, 'x': .5, 'y': .5, 'scale': 1.1, 'rotation': 0}],
        'layers': [{'id': 'bg', 'role': 'background', 'z_index': 0}, {'id': 'char', 'role': 'character', 'z_index': 1}],
        'lights': [], 'transition': {'in': 'cut', 'out': 'cut', 'fraction': 0},
        'continuity': {'entry': 'same person', 'exit': 'reaction cut', 'screen_direction': 'right', 'light_direction': 'left'}}
    prepared = {'id': 'prepared', 'metadata': {'fingerprint': 'prep-hash',
        'input': {'source_psd': {'id': 'psd'}}, 'result': {'source_asset_id': 'psd',
        'source_sha256': 'a' * 64, 'plan_sha256': canonical_plan_sha256(plan), 'plan': plan,
        'files': [{'role': 'source_preview', 'sha256': 'd' * 64}]}}}
    scene = {'number': 2, 'start': 2, 'end': 4, 'image': None, 'ae_scene': prepared}
    snapshot = {'audio': {'id': 'audio', 'metadata': {'sha256': 'e' * 64}}, 'subtitles': [], 'scenes': [scene],
        'sequence_scenes': [{'number': 1, 'start': 0, 'end': 2, 'image': {'id': 'image'}}, scene]}
    review = complete_review(scene, snapshot['audio'], 'c' * 64)
    metadata = {'kind': 'ae_scene_output', 'artifact_ready': True, 'timing_locked': True,
        'voice_synced': True, 'source_audio_id': 'audio', 'source_image_id': None,
        'duration_seconds': 2, 'render_sha256': 'c' * 64, 'ae_mouth_fingerprint': 'job-hash',
        'ae_reviewed': True, 'ae_scene_review': review,
        'ae_scene_preparation_id': 'prepared', 'ae_scene_preparation_fingerprint': 'prep-hash',
        'source_psd_id': 'psd', 'source_sha256': 'a' * 64, 'plan_sha256': prepared['metadata']['result']['plan_sha256']}
    asset = {'id': 'output', 'asset_type': 'video', 'status': 'uploaded', 'scene_number': 2, 'metadata': metadata}
    result = {'number': 2, 'status': 'artifact_ready', 'asset_id': 'output',
        'render_sha256': 'c' * 64, 'output_review': review}
    meta = {'state': 'processing', 'phase': 'auto_enqueue', 'pipeline_version': 2,
        'fingerprint': 'job-hash', 'input': snapshot, 'results': [result]}
    return scene, snapshot, asset, meta


def test_required_ae_artifact_reuse_requires_exact_preparation_and_review():
    scene, snapshot, asset, meta = fixture()
    ready = ready_scene_artifacts(snapshot, [asset], meta['fingerprint'])
    assert ready[2]['output_review']['passed'] is True
    for key, value in [('ae_reviewed', False), ('plan_sha256', 'wrong'),
                       ('source_psd_id', 'wrong'), ('ae_scene_preparation_fingerprint', 'old'),
                       ('ae_scene_review', {'passed': True, 'render_sha256': 'wrong'})]:
        wrong = {**asset, 'metadata': {**asset['metadata'], key: value}}
        assert ready_scene_artifacts(snapshot, [wrong], meta['fingerprint']) == {}


def test_required_scene_never_accepts_skipped_or_missing_output_review():
    _, snapshot, _, meta = fixture()
    validate_required_scene_results(snapshot, meta['results'])
    for rows in [[], [{'number': 2, 'status': 'skipped', 'fallback': 'original'}],
                 [{**meta['results'][0], 'output_review': {'passed': False}}], meta['results'] * 2]:
        with pytest.raises(ValueError, match='needs rendered-output review'):
            validate_required_scene_results(snapshot, rows)


def test_sequence_receipt_identity_changes_when_selected_output_changes():
    _, _, _, meta = fixture()
    expected = hashlib.sha256(json.dumps(['job-hash', [[2, 'artifact_ready', 'output', 'c' * 64]]],
        separators=(',', ':')).encode()).hexdigest()
    assert sequence_fingerprint(meta) == expected
    meta['results'][0]['render_sha256'] = 'd' * 64
    assert sequence_fingerprint(meta) != expected


def test_required_render_is_not_published_without_output_review(monkeypatch, tmp_path):
    import ae_mouth_worker as worker
    scene, snapshot, _, meta = fixture()
    video = tmp_path / 'output.mp4'; video.write_bytes(b'video')
    checksum = hashlib.sha256(b'video').hexdigest()
    rendered = {'output': video, 'render_sha256': checksum, 'review': {'passed': False}}
    monkeypatch.setitem(sys.modules, 'ae_scene_production', SimpleNamespace(render_scene=lambda *args: rendered))
    monkeypatch.setattr(worker.ae, '_upload_gcs_file', lambda *args: pytest.fail('unreviewed output was uploaded'))
    with pytest.raises(ValueError, match='no matching rendered-file review'):
        worker.render_required_ae_scene({'id': 'job', 'project_id': 'p', 'metadata': meta}, scene,
            tmp_path / 'audio', tmp_path / 'scene', lambda: None, object(), 'assets', {})


def test_required_render_publishes_frozen_psd_and_voice_identity(monkeypatch, tmp_path):
    import ae_mouth_worker as worker
    scene, snapshot, _, meta = fixture()
    video = tmp_path / 'output.mp4'; video.write_bytes(b'video')
    checksum = hashlib.sha256(b'video').hexdigest()
    def render(enriched, *args):
        assert enriched['audio'] == snapshot['audio']
        assert enriched['subtitles'] == []
        return {'output': video, 'render_sha256': checksum,
                'review': complete_review(scene, snapshot['audio'], checksum)}
    monkeypatch.setitem(sys.modules, 'ae_scene_production', SimpleNamespace(render_scene=render))
    monkeypatch.setattr(worker, 'subprocess_probe', lambda path: 2)
    monkeypatch.setattr(worker.ae, '_upload_gcs_file', lambda *args: ('bucket', 'output.mp4', ''))
    calls = []
    def request(method, *args, **kwargs):
        calls.append((method, kwargs))
        return SimpleNamespace(json=lambda: [] if method == 'GET' else [{'id': 'output'}])
    monkeypatch.setattr(worker.ae, '_request', request)
    result = worker.render_required_ae_scene({'id': 'job', 'project_id': 'p', 'metadata': meta}, scene,
        tmp_path / 'audio', tmp_path / 'scene', lambda: None, object(), 'assets', {})
    saved = calls[-1][1]['json']['metadata']
    assert saved['ae_scene_preparation_id'] == 'prepared' and saved['source_audio_id'] == 'audio'
    assert saved['source_psd_id'] == 'psd' and saved['ae_reviewed'] is True
    assert result['status'] == 'artifact_ready' and result['output_review']['render_sha256'] == checksum


def test_sequence_review_failure_never_calls_final_enqueue(monkeypatch, tmp_path):
    import ae_mouth_automation as auto
    import requests
    _, _, _, meta = fixture()
    monkeypatch.setattr(auto, 'review_required_sequence', lambda *args: (_ for _ in ()).throw(ValueError('adjacent face changed')))
    monkeypatch.setattr(requests, 'post', lambda *args, **kwargs: pytest.fail('sequence failed but final render enqueued'))
    auto.run_phase(None, {'project_id': 'p'}, meta, tmp_path, None, lambda: None,
                   lambda **changes: meta.update(changes), lambda: False)
    assert meta['state'] == 'failed' and meta['phase'] == 'sequence_review'
    assert meta['auto_pending'] is False


def test_real_sequence_review_receipt_binds_downloaded_output_and_neighbors(monkeypatch, tmp_path):
    import ae_mouth_automation as auto
    _, snapshot, asset, meta = fixture()
    checksum = hashlib.sha256(b'video').hexdigest()
    asset['metadata']['render_sha256'] = checksum
    asset['metadata']['ae_scene_review']['render_sha256'] = checksum
    meta['results'][0]['render_sha256'] = checksum
    monkeypatch.setattr(auto.ae, '_supabase', lambda: ('db', {}))
    monkeypatch.setattr(auto, 'load_project_assets', lambda *args: [asset])
    def download(source, path): path.write_bytes(b'video'); return path
    monkeypatch.setattr(auto, '_download', download)
    def review(scenes, outputs, *args):
        assert [s['number'] for s in scenes] == [1, 2]
        assert outputs[2].read_bytes() == b'video'
        return complete_sequence(meta)
    monkeypatch.setitem(sys.modules, 'ae_scene_production', SimpleNamespace(review_sequence=review))
    receipt = auto.review_required_sequence(object(), {'project_id': 'p'}, meta, tmp_path, lambda: None)
    assert receipt['fingerprint'] == sequence_fingerprint(meta)
    assert [(entry['from'], entry['to']) for entry in receipt['checked_boundaries']] == [(1, 2)]


@pytest.mark.parametrize('mutate', [
    lambda review: review.update(source_sha256='0' * 64),
    lambda review: review.update(plan_sha256='0' * 64),
    lambda review: review.update(source_preview_sha256='0' * 64),
    lambda review: review['audio'].update(source_audio_id='another-recording'),
    lambda review: review['audio'].update(final_audio_sha256='0' * 64),
    lambda review: review['audio'].update(scene_start_seconds=0),
    lambda review: review['audio'].update(correlation=.2),
    lambda review: review.update(batches=[]),
    lambda review: review['batches'][0].update(frames=[]),
    lambda review: review['batches'][0]['review']['checks'].pop(),
    lambda review: review['batches'][0].update(seconds=[0], frames=[{'seconds': 0, 'sha256': 'f' * 64}]),
])
def test_flags_or_wrong_source_voice_and_incomplete_frame_evidence_cannot_reuse_output(mutate):
    scene, snapshot, asset, meta = fixture()
    mutate(asset['metadata']['ae_scene_review'])
    assert not render_review_matches(scene, snapshot['audio'], asset['metadata']['ae_scene_review'], 'c' * 64)
    assert ready_scene_artifacts(snapshot, [asset], meta['fingerprint']) == {}
    with pytest.raises(ValueError, match='needs rendered-output review'):
        validate_required_scene_results(snapshot, meta['results'])


def test_sequence_receipt_requires_every_actual_boundary_and_matching_media():
    _, snapshot, _, meta = fixture()
    valid = complete_sequence(meta)
    assert sequence_review_matches(snapshot['sequence_scenes'], meta['results'], valid)
    for mutation in (
        lambda review: review.update(checked_boundaries=[]),
        lambda review: review['checked_boundaries'][0].update(to=3),
        lambda review: review['checked_boundaries'][0]['evidence'][0].update(source_asset_id='wrong-image'),
        lambda review: review['checked_boundaries'][0]['evidence'][1].update(media_sha256='0' * 64),
        lambda review: review['checked_boundaries'][0]['evidence'][1].update(frames=[]),
        lambda review: review['checked_boundaries'][0]['review']['checks'].pop(),
    ):
        invalid = copy.deepcopy(valid)
        mutation(invalid)
        assert not sequence_review_matches(snapshot['sequence_scenes'], meta['results'], invalid)
