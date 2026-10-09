"""Analyze submitted dialogue videos and persist reusable per-frame geometry before AE."""
import copy
import dataclasses
import uuid
import hashlib
import json
from pathlib import Path

import ae_highlight_worker as ae
from ae_media_utils import ref, ffmpeg, run
from ae_mouth import digest, locate_speakers, visible_speakers
from ae_video_tracking import track_video
from std_project_assets import load_project_assets


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def prepare_submitted_video(runner, project_id, scene, rows, cast, directory, fresh, allow_analyze=True):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    base, headers = ae._supabase()
    source = scene['original_video']
    bucket, path = ref(source)
    video = directory / 'original-video.mp4'
    # Validate current bytes even on resume; an object may have been replaced at the same path.
    ae._download_gcs_file(ae.GcsRef(bucket, path), video)
    video_hash = digest(video)
    names = list(dict.fromkeys(r['speaker'] for r in rows))
    manual = scene.get('speaker_regions') or {}
    expected_hash = ((scene.get('image') or {}).get('metadata') or {}).get('source_video_sha256')
    if expected_hash and video_hash != expected_hash:
        raise ValueError('저장된 기준 프레임의 영상이 변경됐습니다. 영상 좌표를 다시 확인해 주세요.')
    key = fingerprint({'version': 1, 'video': source, 'video_sha256': video_hash, 'cast': cast,
        'rows': rows, 'duration': scene['end'] - scene['start'], 'regions': manual,
        'reference': scene.get('image') if manual else None})
    assets = load_project_assets(ae._request, base, headers, project_id)
    cached = next((a for a in assets if (a.get('metadata') or {}).get('kind') == 'submitted_video_coordinates'
                   and a['metadata'].get('fingerprint') == key and a['metadata'].get('state') == 'ready'), None)
    receipt_file, first = directory / 'video-coordinates.json', directory / 'video-first-frame.png'
    if cached:
        cb, cp = ref(cached)
        ae._download_gcs_file(ae.GcsRef(cb, cp), receipt_file)
        if digest(receipt_file) != cached['metadata']['receipt_sha256']:
            raise ValueError('저장된 영상 좌표 파일이 일치하지 않습니다.')
        receipt = json.loads(receipt_file.read_text(encoding='utf-8'))
        if receipt['fingerprint'] != key or receipt['report']['video_sha256'] != video_hash:
            raise ValueError('영상 좌표의 원본 정보가 일치하지 않습니다.')
        frame = receipt['reference']
        ae._download_gcs_file(ae.GcsRef(frame['gcs_bucket'], frame['gcs_path']), first)
        if digest(first) != frame['sha256']:
            raise ValueError('영상 좌표의 기준 프레임이 일치하지 않습니다.')
        fresh()
        return video, first, receipt['visibility'], receipt['speakers'], receipt['report'], cached['id']
    if not allow_analyze:
        raise ValueError('승인된 영상 좌표 결과가 없습니다. 자동 분석과 연출 확인을 다시 진행해 주세요.')
    fresh()
    run([ffmpeg(), '-hide_banner', '-loglevel', 'error', '-y', '-i', str(video),
         '-map', '0:v:0', '-frames:v', '1', '-an', str(first)])
    reference = first
    supplied = {r['speaker']: r for r in manual.get('speakers', [])}
    if supplied:
        if not scene.get('image') or manual.get('image_id') != scene['image']['id']:
            raise ValueError('저장된 화자 좌표의 기준 이미지가 일치하지 않습니다.')
        rb, rp = ref(scene['image'])
        reference = directory / 'manual-reference.png'
        ae._download_gcs_file(ae.GcsRef(rb, rp), reference)
        if digest(reference) != manual.get('source_sha256'):
            raise ValueError('사용자가 지정한 기준 이미지가 변경됐습니다.')
    missing = [name for name in names if name not in supplied]
    automatic = []
    if missing:
        config = getattr(runner, 'config', None)
        try:
            if config is not None:
                runner.config = dataclasses.replace(config, timeout_seconds=min(config.timeout_seconds, 180))
            automatic = locate_speakers(runner, key + '-' + str(uuid.uuid4()), scene, first,
                                        [r for r in rows if r['speaker'] in missing], cast)
        finally:
            if config is not None:
                runner.config = config
        # Absence in a single frame is not evidence of absence throughout a video.
        if any(s['status'] != 'visible' for s in automatic):
            raise ValueError('영상 첫 프레임에서 화자를 찾지 못했습니다. 등장 구간과 화자 위치를 확인해 주세요.')
        # Mixing coordinate systems is unsafe when a manual seed uses a different image.
        if supplied and digest(reference) != digest(first):
            raise ValueError('일부 화자의 기준 이미지가 영상 첫 프레임과 다릅니다. 모든 화자 위치를 확인해 주세요.')
    by_name = {**{r['speaker']: r for r in automatic}, **supplied}
    visibility = visible_speakers({'speakers': [by_name.get(name, {}) for name in names]}, names)
    speakers = [copy.deepcopy(s) for s in visibility if s['status'] == 'visible']
    if any(not s.get('face_box') for s in speakers):
        raise ValueError('영상 화자의 얼굴 좌표가 없습니다.')
    if speakers:
        first, speakers, report = track_video(video, reference, speakers, directory / 'tracking', scene['end'] - scene['start'])
    else:
        report = {'version': 1, 'video_sha256': video_hash, 'speakers': [], 'source_duration': 0}
    fresh()
    prefix = f'std-projects/{project_id}/video-coordinates/{source["id"]}/{key}'
    fb, fp, _ = ae._upload_gcs_file(first, prefix + '/reference.png', 'image/png')
    receipt = {'version': 1, 'fingerprint': key, 'scene_number': scene['number'],
        'source_video_id': source['id'], 'source_video_path': path,
        'reference': {'gcs_bucket': fb, 'gcs_path': fp, 'sha256': digest(first)},
        'visibility': visibility, 'speakers': speakers, 'report': report}
    receipt_file.write_text(json.dumps(receipt, ensure_ascii=False), encoding='utf-8')
    rb, rp, _ = ae._upload_gcs_file(receipt_file, prefix + '/coordinates.json', 'application/json')
    fresh()
    published = ae._request('POST', base + '/rest/v1/std_project_assets', {**headers, 'Prefer': 'return=representation'}, json={
        'project_id': project_id, 'scene_number': scene['number'], 'asset_type': 'other', 'status': 'uploaded',
        'file_name': f'video-coordinates-{scene["number"]}.json', 'mime_type': 'application/json',
        'metadata': {'kind': 'submitted_video_coordinates', 'state': 'ready', 'fingerprint': key,
            'storage_provider': 'gcs', 'gcs_bucket': rb, 'gcs_path': rp, 'receipt_sha256': digest(receipt_file),
            'source_video_id': source['id'], 'source_video_sha256': video_hash,
            'reference': receipt['reference'], 'report': report, 'origin': 'submission',
            'manual_seed_used': bool(supplied)},
    }).json()
    if not published:
        raise RuntimeError('영상 좌표 분석 결과를 저장하지 못했습니다.')
    return video, first, visibility, speakers, report, published[0]['id']
