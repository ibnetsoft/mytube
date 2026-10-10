"""Post-submission AE mouth jobs; no external lip-sync service or new voice call."""
from __future__ import annotations

import argparse
import copy
import json
import logging
import os
from pathlib import Path
import sys
import time
import threading
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'worker'))
import worker_config
import ae_highlight_worker as ae
from ae_mouth import (assess_dialogue, locate_speakers, mouth_layers, amplitude_cues,
                      audio_reactive_light_cues, decode_scene_audio, review_layers,
                      digest, direction_text, visible_speakers, eye_layers,
                      review_eye_layers, blink_cues)
from codex_content_runner import CodexStagedContentRunner
from manga_layer_generation import NativeCodexLayerGenerator
from ae_video_tracking import track_video
from submitted_video_coordinates import prepare_submitted_video
from ae_media_utils import ffmpeg, run, ref
from std_project_assets import load_project_assets
from ae_mouth_runtime import Heartbeat, instance_lock, claimable_filter
from ae_mouth_automation import automatic_phase, run_phase
from shutdown_flag import clear_shutdown_flag, is_shutdown_requested


class LeaseLost(RuntimeError):
    pass


class Obsolete(RuntimeError):
    pass


def input_matches(snapshot: dict, project: dict, assets: list[dict], scenes: list[dict]) -> bool:
    """Recheck original inputs, never treat our new video as a replacement source image."""
    payload = project.get('project_payload') or {}
    structure = payload.get('structure') or {}
    if (payload.get('tts_speed', (project.get('progress_payload') or {}).get('tts_speed')) != snapshot.get('tts_speed')):
        return False
    audio = next((a for a in assets if a.get('asset_type') == 'audio' and a.get('status') in ('uploaded', 'assigned')
                  and ((a.get('metadata') or {}).get('subtitle_timeline') or a.get('id') == snapshot['audio']['id'])), None)
    if not audio or snapshot['audio'] != {'id': audio['id'], 'metadata': audio.get('metadata')}:
        return False
    saved = payload.get('subtitles') or []
    if len(saved) != len(snapshot['subtitles']):
        return False
    for row, original in zip(saved, snapshot['subtitles']):
        if (row.get('text') != original['text'] or int(row.get('scene_number', row.get('scene', row.get('sceneNumber', 0)))) != original['scene_number']
                or (row.get('dialogue_kind') or '') != original['kind'] or (row.get('dialogue_speaker') or '') != original['speaker']
                or str(row.get('direction') or '') != original.get('direction', '')
                or str(row.get('voice_id') or row.get('voiceId') or '') != str(original['voice_id'])
                or abs(float(row.get('start', row.get('start_num', row.get('start_time', -1)))) - original['start']) > .12
                or abs(float(row.get('end', row.get('end_num', row.get('end_time', -1)))) - original['end']) > .12):
            return False
    cast = {'main': structure.get('main_character') or payload.get('main_character') or {},
            'supporting': structure.get('supporting_characters') or payload.get('supporting_characters') or [],
            'scene_cast': structure.get('scene_cast') or []}
    if cast != snapshot['cast'] or (structure.get('dialogue_annotations') or {}) != snapshot['annotations']:
        return False
    current_numbers = [int(s['scene_number']) for s in scenes if int(s['scene_number']) >= 19 or
        (snapshot.get('version',1) >= 2 and any(int(r.get('scene_number') or 0)==int(s['scene_number']) and r.get('dialogue_kind')=='dialogue' for r in saved)
         and any(a.get('asset_type')=='video' and int(a.get('scene_number') or 0)==int(s['scene_number']) and a.get('status') in ('uploaded','assigned')
                 and not (a.get('metadata') or {}).get('ae_mouth_fingerprint') and not (a.get('metadata') or {}).get('lipsync_fingerprint')
                 and not (a.get('metadata') or {}).get('region_motion_plan_id')
                 and (a.get('metadata') or {}).get('postprocess_mode') not in ('after_effects', 'region_motion') for a in assets))]
    if current_numbers != [s['number'] for s in snapshot['scenes']]:
        return False
    for original in snapshot['scenes']:
        number = original['number']
        s = next(s for s in scenes if int(s['scene_number']) == number)
        source = next((r for r in structure.get('scenes', []) if int(r.get('scene_number') or r.get('scene_order') or 0) == number), s)
        image = next((a for a in assets if a.get('asset_type') == 'image' and int(a.get('scene_number') or 0) == number and a.get('status') in ('uploaded', 'assigned')), None)
        video = next((a for a in assets if a.get('asset_type') == 'video' and int(a.get('scene_number') or 0) == number
                      and a.get('status') in ('uploaded', 'assigned') and not (a.get('metadata') or {}).get('ae_mouth_fingerprint')
                      and not (a.get('metadata') or {}).get('lipsync_fingerprint') and not (a.get('metadata') or {}).get('region_motion_plan_id')
                      and (a.get('metadata') or {}).get('postprocess_mode') not in ('after_effects', 'region_motion')), None)
        reference = next((a for a in assets if video and a.get('status') in ('uploaded', 'assigned')
            and int(a.get('scene_number') or 0) == number and (a.get('metadata') or {}).get('kind') == 'speaker_video_reference'
            and a['metadata'].get('source_video_id') == video['id']
            and a['metadata'].get('source_video_path') == (video.get('metadata', {}).get('gcs_path') or video.get('metadata', {}).get('storage_path'))), None)
        image = reference or image
        if original['image'] != ({'id': image['id'], 'metadata': image.get('metadata')} if image else None):
            return False
        if original.get('original_video') != ({'id': video['id'], 'metadata': video.get('metadata')} if video else None):
            return False
        blink_asset = next((a for a in assets if a.get('status') in ('uploaded', 'assigned')
            and int(a.get('scene_number') or 0) == number
            and (a.get('metadata') or {}).get('kind') == 'eye_blink_confirmation'
            and (a.get('metadata') or {}).get('state') == 'confirmed'
            and (a.get('metadata') or {}).get('image_id') == (image or {}).get('id')), None)
        blink = None
        if blink_asset:
            metadata = blink_asset.get('metadata') or {}
            blink = {key: value for key, value in {
                'id': blink_asset['id'], 'version': metadata.get('version'),
                'character': metadata.get('character'), 'image_id': metadata.get('image_id'),
                'source_bucket': metadata.get('source_bucket'), 'source_path': metadata.get('source_path'),
                'source_sha256': metadata.get('source_sha256'), 'left_eye_box': metadata.get('left_eye_box'),
                'right_eye_box': metadata.get('right_eye_box'), 'interval_seconds': metadata.get('interval_seconds'),
                'confirmed_by': metadata.get('confirmed_by'), 'confirmed_at': metadata.get('confirmed_at'),
            }.items() if value is not None}
        if original.get('eye_blink') != blink:
            return False
        layered = ((source.get('metadata') or {}).get('psd_layer_asset')
                   if isinstance(source.get('metadata'), dict) else None)
        current_layered = None
        if isinstance(layered, dict) and layered.get('qa_status') == 'approved':
            path = str(layered.get('gcs_path') or layered.get('storage_path') or layered.get('object_path') or '')
            if path.lower().endswith('.psd'):
                current_layered = {'metadata': {**layered, 'gcs_path': path,
                    'gcs_bucket': layered.get('gcs_bucket') or layered.get('storage_bucket') or 'air-studio-prod'}}
        if original.get('layered_source') != current_layered:
            return False
        direction = {k: source.get(k) for k in ('ae_motion_plan', 'ae_effect_plan', 'ae_directorial_plan')}
        direction['image_prompt'] = source.get('image_prompt') or s.get('image_prompt') or ''
        if direction != original['direction'] or str(s.get('scene_text') or source.get('scene_text') or source.get('narration') or '') != original['text']:
            return False
    return True


def missing_geometry(scene, names):
    if not scene.get('image'):
        return 'missing_reference_image'
    regions = scene.get('speaker_regions') or {}
    if not regions.get('source_sha256'):
        return 'missing_speaker_coordinates'
    by_name = {row.get('speaker'): row for row in regions.get('speakers', [])}
    for name in names:
        row = by_name.get(name) or {}
        if row.get('status') == 'offscreen':
            continue
        if not row.get('face_box') or not row.get('mouth_box'):
            return 'missing_speaker_coordinates'
    return None


def process_one(report=None, should_stop=None) -> bool:
    report = report or (lambda **changes: None)
    should_stop = should_stop or (lambda: False)
    base, headers = ae._supabase()
    jobs = ae._request('GET', base + '/rest/v1/std_project_assets', headers, params={
        'select': '*', 'metadata->>kind': 'eq.ae_mouth_job',
        'or': claimable_filter(),
        'order': 'created_at.asc', 'limit': '1',
    }).json()
    if not jobs:
        return False
    job = jobs[0]
    meta = copy.deepcopy(job['metadata'])
    auto_phase = automatic_phase(meta)
    render_phase = not auto_phase and (meta.get('phase') == 'render' or meta.get('state') == 'direction_approved')
    snapshot, identity = meta['input'], meta['fingerprint']
    directory = ROOT / 'output' / 'codex-local-console' / 'ae-mouth' / identity
    directory.mkdir(parents=True, exist_ok=True)
    project_url = base + '/rest/v1/std_projects'
    assets_url = base + '/rest/v1/std_project_assets'
    scenes_url = base + '/rest/v1/std_project_scenes'

    def fresh():
        if lease_lost.is_set():
            raise LeaseLost('AE mouth job lease was lost')
        projects = ae._request('GET', project_url, headers, params={'select': '*', 'id': 'eq.' + job['project_id']}).json()
        assets = load_project_assets(ae._request, base, headers, job['project_id'])
        scenes = ae._request('GET', scenes_url, headers, params={'select': '*', 'project_id': 'eq.' + job['project_id'], 'order': 'scene_number.asc'}).json()
        if not projects or not input_matches(snapshot, projects[0], assets, scenes):
            raise Obsolete('대본·음성·원본 이미지가 변경되었습니다. 다시 제출해 주세요.')
        return projects[0]

    lease = str(uuid.uuid4())
    lease_lost = threading.Event()
    stopped = threading.Event()
    guard = threading.Lock()
    # Local lock plus a renewed database lease prevent duplicate work across hosts.
    claimed = ae._request('PATCH', assets_url, {**headers, 'Prefer': 'return=representation'},
        params={'id': 'eq.' + job['id'], 'updated_at': 'eq.' + job['updated_at']},
        json={'metadata': {**meta, 'state': 'processing', 'worker_token': lease, 'heartbeat_at': ae._now(), 'phase': auto_phase or ('render' if render_phase else 'discovery')}, 'updated_at': ae._now()}).json()
    if not claimed:
        return False
    meta = claimed[0]['metadata']
    report(status='running', current_job={'id': job['id'], 'project_id': job['project_id'], 'phase': meta['phase']}, progress=0, last_error=None)

    def save(**changes):
        with guard:
            if lease_lost.is_set():
                raise LeaseLost('AE mouth job lease was lost')
            updated = {**meta, **changes, 'heartbeat_at': ae._now()}
            saved = ae._request('PATCH', assets_url, {**headers, 'Prefer': 'return=representation'},
                params={'id': 'eq.' + job['id'], 'metadata->>worker_token': 'eq.' + lease},
                json={'metadata': updated, 'updated_at': ae._now()}).json()
            if not saved:
                lease_lost.set()
                raise LeaseLost('AE mouth job lease was lost')
            meta.update(updated)
            report(progress=round(100 * len(meta.get('results', [])) / max(1, len(snapshot['scenes']))))
            if changes:
                logging.getLogger('ae_mouth_worker').info('Job %s state=%s saved_scenes=%s', job['id'], meta.get('state'), len(meta.get('results', [])))

    def renew():
        while not stopped.wait(15):
            try:
                save()
            except Exception:
                lease_lost.set()
                return
    ticker = threading.Thread(target=renew, daemon=True)
    ticker.start()

    try:
        fresh()
        if auto_phase == 'auto_enqueue':
            run_phase(None, job, meta, directory, None, fresh, save, should_stop)
            return True
        runner = CodexStagedContentRunner()
        generator = None if auto_phase else NativeCodexLayerGenerator()
        # Recheck before each image generation, not just after publishing a long job.
        class CurrentGenerator:
            def generate(self, **kwargs):
                fresh()
                kwargs['work_dir'] = kwargs['work_dir'].with_name(kwargs['work_dir'].name + '-' + job['id'])
                return generator.generate(**kwargs)
        rows = assess_dialogue(runner, identity, snapshot)
        audio_path = directory / 'final-narration.mp3'
        if not audio_path.exists():
            bucket, path = ref(snapshot['audio'])
            ae._download_gcs_file(ae.GcsRef(bucket, path), audio_path)
        if auto_phase:
            run_phase(runner, job, meta, directory, audio_path, fresh, save, should_stop)
            return True
        outcomes = {r['number']: r for r in meta.get('results', [])}
        candidates = ({r['scene_number'] for r in rows if r['kind'] != 'narration'} |
                      {s['number'] for s in snapshot['scenes'] if s.get('eye_blink')})
        for scene in snapshot['scenes']:
            if scene['number'] not in candidates:
                outcomes[scene['number']] = {'number':scene['number'],'duration':scene['end']-scene['start'],'speakers':[], 'status':'skipped','reason':'저장된 자막에 실제 대사가 없는 씬입니다.'}
        save(results=list(outcomes.values()))
        for scene in sorted((s for s in snapshot['scenes'] if s['number'] in candidates), key=lambda s:s['number']):
            number, duration = scene['number'], scene['end'] - scene['start']
            if number in outcomes and (not render_phase or outcomes[number]['status'] != 'direction_approved'):
                continue
            if should_stop():
                # Leave the job processing; persisted scene outcomes resume on next launch.
                return True
            fresh()
            report(current_job={'id': job['id'], 'project_id': job['project_id'], 'scene_number': number, 'phase': meta['phase']})
            scene_rows = [r for r in rows if r['scene_number'] == number]
            dialogue = [r for r in scene_rows if r['kind'] == 'dialogue']
            blink = copy.deepcopy(scene.get('eye_blink'))
            result = {'number': number, 'duration': duration, 'speakers': list(dict.fromkeys(r['speaker'] for r in dialogue)),
                      'eye_blink_plan_id': blink.get('id') if blink else None}
            if any(r['kind'] == 'uncertain' for r in scene_rows):
                outcomes[number] = {**result,
                    'status': 'skipped' if meta.get('automatic') else 'needs_review',
                    'skip_reason': 'uncertain_dialogue_speaker' if meta.get('automatic') else None,
                    'fallback': 'original' if meta.get('automatic') else None,
                    'reason': '대사·화자를 확실히 판별하지 못해 원본 시각 자료를 사용합니다.' if meta.get('automatic') else '대사·화자를 확실히 판별하지 못했습니다. 자막에서 대사와 화자를 확인한 뒤 다시 제출해 주세요.'}
            elif not dialogue and not blink:
                outcomes[number] = {**result, 'status': 'skipped', 'reason': '실제 캐릭터 대사가 없는 내레이션·반응 장면입니다.'}
            else:
                scene_dir = directory / f'scene-{number}'
                scene_dir.mkdir(parents=True, exist_ok=True)
                image = scene_dir / 'original.png'
                auto_video = bool(scene.get('original_video') and meta.get('auto_video_coordinates')
                                  and (not render_phase or outcomes.get(number, {}).get('video_coordinate_asset_id')))
                missing = None if auto_video or not dialogue else missing_geometry(scene, result['speakers'])
                if missing:
                    outcomes[number] = {**result, 'status': 'skipped', 'skip_reason': missing, 'reason': '저장된 화자 좌표 또는 기준 이미지가 없어 건너뜁니다.'}
                    save(results=list(outcomes.values()))
                    continue
                if not auto_video and not image.exists():
                    bucket, path = ref(scene['image'])
                    ae._download_gcs_file(ae.GcsRef(bucket, path), image)
                try:
                    video, tracking, coordinate_asset_id = None, None, None
                    if auto_video:
                        video, image, visibility, speakers, tracking, coordinate_asset_id = prepare_submitted_video(
                            runner, job['project_id'], scene, dialogue, snapshot['cast'], scene_dir, fresh,
                            allow_analyze=not render_phase)
                        result['video_coordinate_asset_id'] = coordinate_asset_id
                        result['coordinate_state'] = 'ready'
                    elif dialogue:
                        regions = scene.get('speaker_regions')
                        if not regions or regions.get('image_id') != scene['image']['id'] or regions.get('source_sha256') != digest(image):
                            raise ValueError('제출 전 얼굴·입 좌표 준비를 완료해 주세요. 원본 이미지가 변경됐거나 저장된 좌표가 없습니다.')
                        names = list(dict.fromkeys(r['speaker'] for r in dialogue))
                        by_name = {r['speaker']:r for r in regions['speakers']}
                        visibility = visible_speakers({'speakers':[by_name.get(name,{}) for name in names]}, names)
                        speakers = [r for r in visibility if r['status'] == 'visible']
                    else:
                        visibility, speakers = [], []
                    if not speakers and not blink:
                        outcomes[number] = {**result, 'status': 'skipped', 'reason': '화자가 화면 밖에 있습니다. 화면 속 듣는 인물의 입은 움직이지 않습니다.'}
                    else:
                        if scene.get('original_video') and not auto_video:
                            video = scene_dir / 'original-video.mp4'
                            if not video.exists():
                                bucket, path = ref(scene['original_video'])
                                ae._download_gcs_file(ae.GcsRef(bucket,path),video)
                            video_hash = (scene['image'].get('metadata') or {}).get('source_video_sha256')
                            if video_hash and digest(video) != video_hash:
                                raise ValueError('기준 프레임의 원본 영상이 변경됐습니다. 영상 좌표를 다시 저장해 주세요.')
                            image, speakers, tracking = track_video(video,image,speakers,scene_dir/'tracking',duration)
                        direction = direction_text(speakers, dialogue, scene['start']) if speakers else ''
                        if blink:
                            direction += (' 사용자가 지정한 ' + str(blink['character']) + '의 양쪽 눈 좌표에만 '
                                          + str(blink['interval_seconds']) + '초 간격의 자연스러운 눈 깜빡임을 적용합니다.')
                        if tracking:
                            direction += ' 원본 영상은 1배속으로 유지하고 얼굴·입의 이동·크기·회전을 추적합니다. 영상 종료 후 입 움직임은 확정된 대사 끝까지 유지하며 마지막 화면에 6% 줌인을 적용합니다.'
                        if not render_phase:
                            outcomes[number] = {**result, 'status': 'direction_pending', 'direction': direction, 'visibility': visibility, 'tracking':tracking}
                            save(results=[outcomes[s['number']] for s in snapshot['scenes'] if s['number'] in outcomes])
                            continue
                        samples = decode_scene_audio(ffmpeg(), audio_path, scene['start'], duration)
                        for index, speaker in enumerate(speakers):
                            speaker['layers'] = mouth_layers(CurrentGenerator(), image, speaker, scene_dir / f'speaker-{index}')
                            speaker['layer_sha256'] = {pose: digest(Path(path)) for pose, path in speaker['layers'].items()}
                            speaker['cues'] = amplitude_cues(samples, [r for r in dialogue if r['speaker'] == speaker['speaker']], start=scene['start'], duration=duration)
                        if speakers:
                            review_layers(runner, f'{identity}-{number}', image, speakers, scene_dir)
                        runtime_blinks = []
                        if blink:
                            if blink.get('image_id') != (scene.get('image') or {}).get('id') or blink.get('source_sha256') != digest(image):
                                raise ValueError('눈 좌표를 지정한 원본 이미지가 변경되었습니다. 다시 지정해 주세요.')
                            blink['layers'] = eye_layers(CurrentGenerator(), image, blink, scene_dir / 'eye-blink')
                            blink['layer_sha256'] = {side: digest(Path(path)) for side, path in blink['layers'].items()}
                            blink['cues'] = blink_cues(duration, float(blink['interval_seconds']))
                            review_eye_layers(runner, f'{identity}-{number}', image, blink, scene_dir / 'eye-blink')
                            runtime_blinks.append(blink)
                        fresh()
                        source_scene = {'scene_number': number, 'scene_text': scene['text'], **copy.deepcopy(scene['direction']),
                                        'ae_mouth_runtime': {'enabled': True, 'speakers': speakers, 'audio_sha256': digest(audio_path),
                                            'blinks': runtime_blinks,
                                            'audio_light_cues': audio_reactive_light_cues(samples, dialogue, start=scene['start'], duration=duration) if dialogue else [],
                                            'video_source':bool(video),'video_duration':tracking['source_duration'] if tracking else None,
                                            'tracking':tracking}}
                        render_source = video or image
                        layered_source = scene.get('layered_source')
                        if layered_source and not video:
                            layered_psd = scene_dir / 'approved-layers.psd'
                            if not layered_psd.exists():
                                bucket, path = ref(layered_source)
                                ae._download_gcs_file(ae.GcsRef(bucket, path), layered_psd)
                            approved = layered_source.get('metadata') or {}
                            if digest(layered_psd) != approved.get('sha256'):
                                raise ValueError('승인된 레이어 PSD의 해시가 변경되었습니다. 레이어 검수를 다시 진행해 주세요.')
                            source_scene['metadata'] = {'psd_layer_asset': copy.deepcopy(approved)}
                            render_source = layered_psd
                        selected = ae._render_plan_from_scene(source_scene)
                        if not selected:
                            source_scene['ae_motion_plan'] = {'enabled': True, 'preset': 'subtle_dialogue', 'vfx': [], 'intensity': .15,
                                                            'motion': {'push': .01, 'drift_x': 0, 'drift_y': 0, 'shake': 0}}
                            selected = ('motion', source_scene['ae_motion_plan'])
                        kind, plan = selected
                        source_scene['duration_seconds'] = duration
                        job_spec = ae.SceneJob(topic_id=job['project_id'], topic_title='AE mouth postprocessing', structure={'scenes': [source_scene]}, scene_index=0,
                            scene=source_scene, scene_number=number, plan_kind=kind, preset=str(plan.get('preset') or 'subtle_dialogue'),
                            duration_seconds=duration, source=ae.GcsRef('__local__', str(render_source.resolve())), source_type='project',
                            project_payload={'ae_scene_delivery': 'local'})
                        # Existing AE effects consume the animated-mouth source precomp, preserving registration.
                        rendered = ae._render_job(job_spec, keep_workdir=True)
                        silent = Path(rendered['local_path'])
                        preview = scene_dir / 'ae-mouth-preview.mp4'
                        run([ffmpeg(), '-y', '-i', str(silent), '-ss', str(scene['start']), '-i', str(audio_path), '-t', str(duration),
                             '-map', '0:v:0', '-map', '1:a:0', '-c:v', 'copy', '-c:a', 'aac', '-ar', '48000', str(preview)])
                        # Probe actual duration before accepting a timing-locked asset.
                        probe = subprocess_probe(preview)
                        if abs(probe - duration) > .12:
                            raise ValueError('AE 영상 길이가 확정된 TTS와 다릅니다. 속도 변경 없이 재검토가 필요합니다.')
                        fresh()
                        object_path = f'std-projects/{job["project_id"]}/ae-mouth/{identity}/scene-{number}-{digest(preview)[:16]}.mp4'
                        bucket, path, _ = ae._upload_gcs_file(preview, object_path, 'video/mp4')
                        # Idempotent recovery: a restarted worker reuses this fingerprint/scene output.
                        assets = ae._request('GET', assets_url, headers, params={'select': '*', 'project_id': 'eq.' + job['project_id'],
                            'scene_number': 'eq.' + str(number), 'asset_type': 'eq.video', 'metadata->>ae_mouth_fingerprint': 'eq.' + identity}).json()
                        asset = next((a for a in assets if a['metadata'].get('render_sha256') == digest(preview)), None)
                        if not asset:
                            asset = ae._request('POST', assets_url, {**headers, 'Prefer': 'return=representation'}, json={
                                'project_id': job['project_id'], 'scene_number': number, 'asset_type': 'video', 'status': 'uploaded',
                                'file_name': f'scene_{number}_ae_mouth.mp4', 'mime_type': 'video/mp4', 'file_size': preview.stat().st_size,
                                'metadata': {'storage_provider': 'gcs', 'gcs_bucket': bucket, 'gcs_path': path, 'storage_bucket': bucket,
                                    'storage_path': path, 'ae_mouth_fingerprint': identity, 'timing_locked': True, 'ae_reviewed': False,
                                    'duration_seconds': duration, 'render_sha256': digest(preview), 'direction': direction,
                                    'source_image_id': (scene.get('image') or {}).get('id'), 'source_audio_id': snapshot['audio']['id'],
                                    'source_video_id':scene['original_video']['id'] if video else None,'video_tracking':tracking,
                                    'video_coordinate_asset_id':coordinate_asset_id,
                                    'eye_blink_plan_id':blink.get('id') if blink else None,
                                    'eye_blink_applied':bool(blink)},
                            }).json()[0]
                        outcomes[number] = {**outcomes.get(number, {}), **result, 'visibility': visibility, 'status': 'review_pending', 'asset_id': asset['id'], 'render_sha256': digest(preview), 'direction': direction,'tracking':tracking}
                except (LeaseLost, Obsolete):
                    raise
                except Exception as exc:
                    if auto_video and not result.get('video_coordinate_asset_id'): result['coordinate_state'] = 'needs_review'
                    outcomes[number] = {**result,
                        'status': 'skipped' if meta.get('automatic') else 'needs_review',
                        'skip_reason': 'automatic_processing_failed' if meta.get('automatic') else None,
                        'fallback': 'original' if meta.get('automatic') else None,
                        'reason': str(exc)[:500]}
            save(results=[outcomes[s['number']] for s in snapshot['scenes'] if s['number'] in outcomes])
        fresh()
        save(state='reviewed' if all(r['status'] == 'skipped' for r in outcomes.values()) else 'review_pending' if render_phase else 'direction_pending', auto_pending=bool(meta.get('automatic')), error='')
    except LeaseLost as exc:
        report(last_error=str(exc))
    except Obsolete as exc:
        save(state='obsolete', error=str(exc))
        report(last_error=str(exc))
    except Exception as exc:
        save(state='failed', error=str(exc)[:500])
        report(last_error=str(exc)[:500])
    finally:
        stopped.set()
        ticker.join(timeout=65)
    return True


def subprocess_probe(path: Path) -> float:
    from media_checkpoint import _mp4_duration_with_first_frame
    stat = path.stat()
    duration = _mp4_duration_with_first_frame(str(path.resolve()), stat.st_size, stat.st_mtime_ns)
    if duration is None:
        raise ValueError('AE 출력 영상의 처음과 끝 프레임을 확인하지 못했습니다.')
    return duration


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--once', action='store_true')
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--coordinates-only', action='store_true')
    mode.add_argument('--mouth-only', action='store_true')
    args, _ = parser.parse_known_args()  # Unified entry point also passes --role/--profile.
    name = 'ae_mouth_worker'
    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)
    handler = logging.FileHandler(worker_config.LOG_FILES[name], encoding='utf-8')
    logger.addHandler(handler)
    try:
        with instance_lock(worker_config.STATE_DIR / (name + '.lock')):
            clear_shutdown_flag(name)
            with Heartbeat(worker_config.STATE_DIR / (name + '.json'), worker_config.WORKER_INSTANCE_ID) as heartbeat:
                logger.info('AIR mouth worker started')
                while not is_shutdown_requested(name):
                    heartbeat.update(status='idle', current_job=None, progress=0)
                    try:
                        # Submitted media takes priority over optional coordinate analysis.
                        handled = False if args.coordinates_only else process_one(
                            report=heartbeat.update, should_stop=lambda: is_shutdown_requested(name))
                        if not handled and not args.mouth_only and not is_shutdown_requested(name):
                            from ae_speaker_coordinates import process_one as prepare_coordinates
                            heartbeat.update(status='running', current_job={'id': 'coordinate-analysis'})
                            prepare_coordinates(should_stop=lambda: is_shutdown_requested(name))
                        if not heartbeat.state.get('last_error'):
                            heartbeat.update(last_success_at=time.time())
                    except Exception as exc:
                        logger.exception('AE mouth poll failed')
                        heartbeat.update(last_error=str(exc)[:500])
                    finally:
                        heartbeat.update(status='idle', current_job=None)
                    if args.once:
                        break
                    for _ in range(20):
                        if is_shutdown_requested(name):
                            break
                        time.sleep(1)
            logger.info('AIR mouth worker stopped')
    finally:
        logger.removeHandler(handler)
        handler.close()


if __name__ == '__main__':
    main()
