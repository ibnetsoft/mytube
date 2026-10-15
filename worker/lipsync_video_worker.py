"""Hedra audio-driven dialogue clips. ElevenLabs narration remains the master audio."""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'worker'))
import worker_config
from comfy_scene_video_worker import _supabase, _request, _download_gcs, _upload_gcs, _now
import requests

API = 'https://api.hedra.com/v3'

def run(command):
    result = subprocess.run(command, capture_output=True, timeout=900)
    if result.returncode:
        raise RuntimeError(result.stderr.decode('utf-8', errors='replace')[-1200:])

def ffmpeg():
    import imageio_ffmpeg
    return imageio_ffmpeg.get_ffmpeg_exe()

def ref(asset):
    m = asset.get('metadata') or {}
    bucket, path = m.get('gcs_bucket') or m.get('storage_bucket'), m.get('gcs_path') or m.get('storage_path')
    if not bucket or not path or m.get('storage_provider') not in (None, 'gcs'):
        raise RuntimeError('GCS input is required')
    return bucket, path

def hedra(key, method, path, **kwargs):
    r = requests.request(method, API + path, headers={'Authorization': 'Key ' + key}, timeout=120, **kwargs)
    if not r.ok:
        # Do not log response bodies containing media handles or credentials.
        code = r.json().get('error', {}).get('code', 'request_failed') if 'json' in r.headers.get('content-type', '') else 'request_failed'
        raise RuntimeError(f'Hedra {r.status_code}: {code}')
    return r.json()

def upload(key, path, mime):
    with path.open('rb') as f:
        return hedra(key, 'POST', '/files', files={'file': (path.name, f, mime)})['url']

def clip_command(source, destination, duration, still=False):
    inputs = ['-loop', '1', '-framerate', '24'] if still else []
    return [ffmpeg(), '-y', *inputs, '-i', str(source), '-an', '-vf',
            'scale=1920:1080:force_original_aspect_ratio=increase,crop=1920:1080,fps=24,tpad=stop_mode=clone:stop_duration=0.1',
            '-frames:v', str(max(1, round(duration * 24))), '-c:v', 'libx264', '-preset', 'veryfast', '-crf', '20', '-pix_fmt', 'yuv420p', str(destination)]

def process_one():
    base, headers = _supabase()
    rows = _request('GET', base + '/rest/v1/std_project_assets', headers, params={
        'select': '*', 'metadata->>kind': 'eq.lipsync_job', 'metadata->>state': 'in.(queued,processing,reviewed)',
        'order': 'created_at.asc', 'limit': '100'}).json()
    rows = [r for r in rows if not r['metadata'].get('ae_reviewed') and r['metadata'].get('ae_state') not in ('ready', 'failed')]
    if not rows:
        return False
    job = rows[0]
    m = job['metadata']
    settings = _request('GET', base + '/rest/v1/global_settings', headers, params={'select': 'value', 'key': 'eq.sys_api_hedra'}).json()
    key = (settings[0].get('value') if settings else '') or os.getenv('HEDRA_API_KEY', '')
    if not key:
        return False
    def save(**patch):
        nonlocal m
        m = {**m, **patch}
        _request('PATCH', base + '/rest/v1/std_project_assets?id=eq.' + job['id'],
                 {**headers, 'Content-Type': 'application/json'}, json={'metadata': m, 'updated_at': _now()})
    project = _request('GET', base + '/rest/v1/std_projects', headers,
                       params={'select': '*', 'id': 'eq.' + job['project_id']}).json()[0]
    current = [{**s, 'start': s.get('start', s.get('start_num', s.get('start_time'))), 'end': s.get('end', s.get('end_num', s.get('end_time')))} for s in (project.get('project_payload') or {}).get('subtitles', [])
               if s.get('dialogue_kind') == 'dialogue' and int(s.get('scene_number') or 0) == job['scene_number']]
    snapshot = m['plan']['shots']
    master_id = (project.get('progress_payload') or {}).get('tts_asset_id')
    changed = (master_id and master_id != m['plan'].get('audio_id')) or len(current) != len(snapshot)
    for a, b in zip(current, snapshot):
        changed = changed or (a.get('text') != b.get('text') or a.get('voice_id') != b.get('voice_id')
                              or (a.get('dialogue_speaker') or a.get('voice_id')) != b.get('speaker')
                              or abs(float(a['start'])-float(b['start'])) > .12 or abs(float(a['end'])-float(b['end'])) > .12)
    for kind in ('audio', 'image'):
        expected = m['plan'].get(kind + '_id')
        if not expected: continue
        params = {'select': 'id', 'project_id': 'eq.' + job['project_id'], 'asset_type': 'eq.' + kind,
                  'status': 'in.(uploaded,assigned)', 'order': 'created_at.desc', 'limit': '1'}
        if kind == 'image': params['scene_number'] = 'eq.' + str(job['scene_number'])
        latest = _request('GET', base + '/rest/v1/std_project_assets', headers, params=params).json()
        changed = changed or not latest or latest[0]['id'] != expected
    if changed:
        save(state='obsolete', error='대사 또는 TTS가 바뀌어 이전 요청을 중단했습니다. 현재 음성으로 다시 요청해 주세요.')
        return True
    if m['state'] == 'reviewed':
        try:
            from ae_highlight_worker import _find_scene_jobs, process_job
            project['__source_type'] = 'project'
            jobs = [j for j in _find_scene_jobs([project]) if j.scene_number == job['scene_number']
                    and (j.scene.get('metadata') or {}).get('lipsync_asset', {}).get('lipsync_fingerprint') == m['fingerprint']]
            if not jobs:
                return False
            save(ae_state='processing')
            process_job(jobs[0], keep_workdir=True)
            save(ae_state='ready', error=None)
        except Exception as e:
            save(ae_state='failed', error=str(e)[:1400])
        return True
    claim = _request('PATCH', base + '/rest/v1/std_project_assets',
                     {**headers, 'Content-Type': 'application/json', 'Prefer': 'return=representation'},
                     params={'id': 'eq.' + job['id'], 'updated_at': 'eq.' + job['updated_at']},
                     json={'metadata': {**m, 'state': 'processing'}, 'updated_at': _now()}).json()
    if not claim:
        return False
    try:
        p = m['plan']
        directory = worker_config.TEMP_DIR / 'lipsync' / job['id']
        directory.mkdir(parents=True, exist_ok=True)
        image, audio = directory / 'image.png', directory / 'master.mp3'
        if not image.exists(): _download_gcs(*ref(p['image']), image)
        if not audio.exists(): _download_gcs(*ref(p['audio']), audio)
        parts = []
        cursor = float(p['start'])
        cursor_frame = 0
        receipts = dict(m.get('provider_jobs') or {})
        for i, shot in enumerate(p['shots']):
            start, end = float(shot['start']), float(shot['end'])
            if start < cursor - .01 or end > float(p['end']) + .01:
                raise RuntimeError('Dialogue overlaps or crosses a scene boundary')
            start_frame = round((start - float(p['start'])) * 24)
            end_frame = round((end - float(p['start'])) * 24)
            if start_frame > cursor_frame:
                still = directory / f'gap_{i}.mp4'
                run(clip_command(image, still, (start_frame - cursor_frame) / 24, still=True))
                parts.append(still)
            raw, cut = directory / f'raw_{i}.mp4', directory / f'shot_{i}.wav'
            if not raw.exists():
                run([ffmpeg(), '-y', '-i', str(audio), '-ss', f'{start:.6f}', '-t', f'{end-start:.6f}', '-vn', '-ar', '48000', '-ac', '1', str(cut)])
                receipt = receipts.get(str(i))
                if not receipt:
                    image_url = upload(key, image, 'image/png')
                    audio_url = upload(key, cut, 'audio/wav')
                    receipt = hedra(key, 'POST', '/models/hedra-character-3', json={
                        'idempotency_key': job['id'] + ':' + str(i), 'input': {
                            'aspect_ratio': '16:9', 'resolution': '1080p',
                            'prompt': 'Preserve the exact character identity, clothing, illustration style and scene. Only the selected speaker speaks the supplied audio. Other characters keep their mouths closed. Subtle natural expression and head motion. No camera cuts, captions or new characters.',
                            'start_image': {'source': 'url', 'url': image_url},
                            'audio': {'source': 'url', 'url': audio_url},
                            'bounding_box_target': m['points'][shot['speaker']]}})
                    receipts[str(i)] = {'job_id': receipt['job_id']}
                    save(provider_jobs=receipts, state='processing')
                deadline = time.time() + 3600
                while time.time() < deadline:
                    status = hedra(key, 'GET', '/jobs/' + receipts[str(i)]['job_id'] + '/status')['status']
                    if status == 'COMPLETED': break
                    if status in ('FAILED', 'CANCELLED', 'EXPIRED'): raise RuntimeError('Hedra job ' + status)
                    time.sleep(15)
                else: raise RuntimeError('Hedra polling timed out; saved job receipt preserved')
                outputs = hedra(key, 'GET', '/jobs/' + receipts[str(i)]['job_id'])['outputs']
                output = next(o for o in outputs if o.get('url') and (o.get('content_type') or '').startswith('video/'))
                if abs(float(output.get('duration_ms') or 0) / 1000 - (end-start)) > .12:
                    raise RuntimeError('Generated duration differs from the voice. Speed changes are forbidden.')
                r = requests.get(output['url'], timeout=180)
                r.raise_for_status()
                partial = raw.with_suffix('.part')
                partial.write_bytes(r.content)
                partial.replace(raw)
            clip = directory / f'clip_{i}.mp4'
            run(clip_command(raw, clip, (end_frame - start_frame) / 24))
            parts.append(clip)
            cursor = end
            cursor_frame = end_frame
        total_frames = round((float(p['end']) - float(p['start'])) * 24)
        if total_frames > cursor_frame:
            tail = directory / 'tail.mp4'
            run(clip_command(image, tail, (total_frames-cursor_frame)/24, still=True))
            parts.append(tail)
        listing = directory / 'concat.txt'
        listing.write_text('\n'.join("file '" + str(f.resolve()).replace('\\', '/').replace("'", "'\\''") + "'" for f in parts), encoding='utf-8')
        output = directory / 'scene.mp4'
        run([ffmpeg(), '-y', '-f', 'concat', '-safe', '0', '-i', str(listing), '-i', str(audio), '-map', '0:v:0', '-map', '1:a:0', '-af', f"atrim=start={float(p['start']):.6f}:end={float(p['end']):.6f},asetpts=PTS-STARTPTS", '-c:a', 'aac', '-c:v', 'copy', '-movflags', '+faststart', str(output)])
        bucket, path = _upload_gcs(output, f"std-projects/{job['project_id']}/lipsync/{job['id']}.mp4")
        metadata = {'storage_provider': 'gcs', 'gcs_bucket': bucket, 'gcs_path': path,
                    'lipsync_fingerprint': m['fingerprint'], 'timing_locked': True,
                    'duration_seconds': float(p['end'])-float(p['start']), 'kind': 'lipsync_video',
                    'lipsync_reviewed': False, 'ae_reviewed': False}
        # Resume after publication without inserting duplicate output assets.
        found = _request('GET', base + '/rest/v1/std_project_assets', headers, params={
            'select': 'id', 'project_id': 'eq.' + job['project_id'], 'metadata->>gcs_path': 'eq.' + path}).json()
        if found: asset = found[0]
        else:
            asset = _request('POST', base + '/rest/v1/std_project_assets', {**headers, 'Content-Type': 'application/json', 'Prefer': 'return=representation'},
                json={'project_id': job['project_id'], 'scene_number': p['scene_number'], 'asset_type': 'video',
                      'file_name': f"scene_{p['scene_number']}_lipsync.mp4", 'mime_type': 'video/mp4',
                      'file_size': output.stat().st_size, 'status': 'assigned', 'metadata': metadata}).json()[0]
        save(state='review_pending', output_asset_id=asset['id'], error=None)
        print('Lipsync ready:', job['project_id'], p['scene_number'], flush=True)
    except Exception as e:
        save(state='failed', error=str(e)[:1400])
        print('Lipsync failed:', job['id'], type(e).__name__, flush=True)
    return True

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--once', action='store_true')
    args = parser.parse_args()
    # One local orchestrator: an OS file lock is released on process exit.
    import msvcrt
    lock_path = worker_config.STATE_DIR / 'lipsync_worker.lock'
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open('a+b') as lock:
        lock.seek(0)
        try: msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError: sys.exit('Lipsync worker is already running')
        while True:
            try: process_one()
            except Exception as e: print('Lipsync poll:', type(e).__name__, flush=True)
            if args.once: break
            time.sleep(20)
