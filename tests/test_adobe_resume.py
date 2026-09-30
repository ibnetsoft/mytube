"""Restart and retry behavior for the local Adobe workers."""
from __future__ import annotations

import json
import pathlib
import sys

import pytest


ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'worker'))


def test_ae_resume_reuses_render_after_upload_failure(monkeypatch, tmp_path):
    import ae_highlight_worker as worker

    monkeypatch.setattr(worker.worker_config, 'TEMP_DIR', tmp_path)
    monkeypatch.setattr(worker, 'write_state', lambda *args, **kwargs: None)
    executable = tmp_path / 'adobe.exe'
    executable.write_bytes(b'app')
    monkeypatch.setattr(worker, 'find_afterfx', lambda: executable)
    monkeypatch.setattr(worker, 'find_aerender', lambda: executable)
    calls = {'download': 0, 'project': 0, 'render': 0, 'upload': 0}

    def download(_ref, target):
        calls['download'] += 1
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b'i' * 2048)

    def project(_app, _script, target, **_kwargs):
        calls['project'] += 1
        target.write_bytes(b'p' * 2048)

    def render(command, **_kwargs):
        calls['render'] += 1
        pathlib.Path(command[-1]).write_bytes(b'v' * 2048)

    def upload(_path, key, _mime):
        calls['upload'] += 1
        if calls['upload'] == 1:
            raise RuntimeError('temporary upload error')
        return 'bucket', key, 'gs://bucket/' + key

    monkeypatch.setattr(worker, '_download_gcs_file', download)
    monkeypatch.setattr(worker, '_run_afterfx_script', project)
    monkeypatch.setattr(worker, '_run_checked', render)
    monkeypatch.setattr(worker, '_upload_gcs_file', upload)
    monkeypatch.setattr(worker, 'valid_mp4', lambda path, *_args: path.is_file())
    scene = {'ae_motion_plan': {'enabled': True, 'preset': 'subtle_motion'}}
    job = worker.SceneJob('3285', 'wuxia', {'scenes': [scene]}, 0, scene, 1,
                          'motion', 'subtle_motion', 2.0, worker.GcsRef('bucket', 'scene.png'))
    with pytest.raises(RuntimeError, match='temporary upload'):
        worker._render_job(job)
    result = worker._render_job(job)
    assert result['media_url'].startswith('gs://')
    assert calls == {'download': 1, 'project': 1, 'render': 1, 'upload': 2}


def test_ae_failed_scene_waits_then_needs_attention(monkeypatch):
    import ae_highlight_worker as worker

    monkeypatch.setattr(worker, 'write_state', lambda *args, **kwargs: None)
    monkeypatch.setattr(worker, '_patch_job_structure', lambda *_args, **_kwargs: None)
    monkeypatch.setattr(worker, '_render_job', lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError('AE failed')))
    scene = {'ae_motion_plan': {'enabled': True},
             'image_url': '/api/std/assets/gcs-file?bucket=b&path=i.png'}
    structure = {'scenes': [scene]}
    job = worker.SceneJob('1', 'test', structure, 0, scene, 1, 'motion', 'subtle_motion', 2,
                          worker.GcsRef('b', 'i.png'))
    with pytest.raises(RuntimeError):
        worker.process_job(job)
    asset = scene['metadata']['ae_motion_asset']
    assert asset['status'] == 'retry_wait' and asset['next_retry_at'] > 0
    row = {'id': '1', '__source_type': 'project', 'project_payload': {'structure': structure}}
    assert worker._find_scene_jobs([row]) == []
    asset['next_retry_at'] = 0
    asset['attempts'] = worker.MAX_ATTEMPTS - 1
    with pytest.raises(RuntimeError):
        worker.process_job(job)
    assert scene['metadata']['ae_motion_asset']['status'] == 'needs_attention'
    assert worker._find_scene_jobs([row]) == []


def test_final_worker_waits_for_ae_and_reuses_uploads(monkeypatch, tmp_path):
    import premiere_final_worker as worker

    scene = {'scene_number': 1, 'duration_seconds': 2,
             'image_url': '/api/std/assets/gcs-file?bucket=b&path=i.png',
             'ae_motion_plan': {'enabled': True, 'preset': 'subtle_motion'}}
    row = {'id': 'project', 'title': 'wuxia', 'submitted_at': '2026-09-26T00:00:00Z',
           'project_payload': {'structure': {'scenes': [scene]}}, 'progress_payload': {}}
    assert worker.find_project_jobs([row]) == []
    scene['ae_motion_video_url'] = '/api/std/assets/gcs-file?bucket=b&path=v.mp4'
    job = worker.find_project_jobs([row])[0]

    monkeypatch.setattr(worker, 'PACKAGE_ROOT', tmp_path)
    monkeypatch.setattr(worker, 'STATE_FILE', tmp_path / 'state.json')
    monkeypatch.setattr(worker, 'write_state', lambda *args, **kwargs: (tmp_path / 'state.json').write_text('{}'))
    monkeypatch.setattr(worker, '_update_project', lambda *_args: None)
    monkeypatch.setenv('PREMIERE_FINAL_BACKEND', 'ffmpeg')
    calls = {'download': 0, 'render': 0, 'upload': []}

    def download(_ref, target):
        calls['download'] += 1
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b'i' * 2048)

    def render(_clips, _audio, _srt, target):
        calls['render'] += 1
        target.write_bytes(b'v' * 2048)

    def upload(_path, key, _mime):
        calls['upload'].append(key)
        if len(calls['upload']) == 2:
            raise RuntimeError('network timeout')
        return 'bucket', key, 'gs://bucket/' + key

    monkeypatch.setattr(worker, '_download_gcs_file', download)
    monkeypatch.setattr(worker, '_render_final_mp4', render)
    monkeypatch.setattr(worker, '_upload_gcs_file', upload)
    monkeypatch.setattr(worker, 'valid_mp4', lambda path, *_args: path.is_file())
    with pytest.raises(RuntimeError, match='network timeout'):
        worker.process_job(job)
    result = worker.process_job(job)
    assert result['status'] == 'ready'
    assert calls['download'] == 1 and calls['render'] == 1
    assert calls['upload'].count('projects/project/premiere/final-package/air-premiere-manifest.json') == 1


def test_final_worker_never_uses_uploaded_source_video_before_ae_postprocess():
    import premiere_final_worker as worker

    scene = {
        'scene_number': 1,
        'video_generation_mode': 'user_upload',
        'video_url': '/api/std/assets/gcs-file?bucket=b&path=source.mp4',
        'ae_motion_plan': {'enabled': True, 'input_source': 'uploaded_video_asset'},
    }
    assert worker._scene_media_ref(scene) == ('', None)

    scene['ae_motion_video_url'] = '/api/std/assets/gcs-file?bucket=b&path=ae-finished.mp4'
    key, ref = worker._scene_media_ref(scene)
    assert key == 'ae_motion_video_url'
    assert ref is not None and ref.path == 'ae-finished.mp4'


def test_ae_postprocesses_uploaded_scene_clip_only_after_video_registration():
    import ae_highlight_worker as ae

    scene = {
        'scene_number': 1,
        'video_generation_mode': 'user_upload',
        'ae_motion_plan': {'enabled': True, 'input_source': 'uploaded_video_asset'},
        'metadata': {'video_generation_mode': 'user_upload'},
    }
    row = {'id': 'project', '__source_type': 'project', 'title': 'test', 'submitted_at': '2026-09-26T00:00:00Z',
           'project_payload': {'structure': {'scenes': [scene]}}}
    assert ae._find_scene_jobs([row]) == []

    scene['metadata']['video_asset'] = {'gcs_bucket': 'b', 'gcs_path': 'projects/p/upload.mp4'}
    jobs = ae._find_scene_jobs([row])
    assert len(jobs) == 1
    assert jobs[0].source.path == 'projects/p/upload.mp4'


def test_final_failure_backoff_and_terminal_state(monkeypatch):
    import premiere_final_worker as worker

    row = {'id': 'project', 'title': 'test', 'submitted_at': '2026-09-26T00:00:00Z',
           'project_payload': {'structure': {'scenes': [{
               'scene_number': 1, 'image_url': '/api/std/assets/gcs-file?bucket=b&path=i.png'}]}},
           'progress_payload': {}}
    recorded = []
    monkeypatch.setattr(worker, '_update_project', lambda _job, asset: recorded.append(asset))
    job = worker.find_project_jobs([row])[0]
    worker._record_project_failure(job, RuntimeError('AME busy'))
    assert recorded[-1]['status'] == 'retry_wait'
    row['project_payload']['render_settings'] = {'premiere_final_asset': recorded[-1]}
    assert worker.find_project_jobs([row]) == []
    row['project_payload']['render_settings']['premiere_final_asset']['attempts'] = worker.MAX_ATTEMPTS - 1
    worker._record_project_failure(worker.find_project_jobs([row], force=True)[0], RuntimeError('AME busy'))
    assert recorded[-1]['status'] == 'needs_attention'
