"""Prepare missing still-image mouth data against actual submitted pixels."""
import copy
import json
from pathlib import Path

from ae_mouth import digest, locate_speakers, visible_speakers
from mouth_geometry import validate
from submitted_video_coordinates import fingerprint


def prepare(runner, job, scene, postwork, image, directory, fresh):
    import ae_highlight_worker as ae
    from ae_media_utils import ref
    from std_project_assets import load_project_assets
    from prepared_mouth_layers import prepare_scene
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    fresh()
    source_hash = digest(image)
    names = list(dict.fromkeys(row['speaker'] for row in postwork['dialogue']))
    regions = copy.deepcopy(postwork.get('speaker_regions'))
    receipt_id = None
    if regions:
        if regions.get('image_id') != scene['source']['id'] or regions.get('source_sha256') != source_hash:
            raise ValueError('Prepared still mouth source changed')
    else:
        base, headers = ae._supabase()
        key = fingerprint({'version': 1, 'source_id': scene['source']['id'],
            'source': ref(scene['source']), 'source_sha256': source_hash,
            'cast': postwork['cast'], 'speakers': names})
        assets = load_project_assets(ae._request, base, headers, job['project_id'])
        cached = next((a for a in assets if a.get('status') in ('uploaded', 'assigned')
                       and a.get('scene_number') == scene['number']
                       and (a.get('metadata') or {}).get('kind') == 'submitted_still_coordinates'
                       and a['metadata'].get('fingerprint') == key and a['metadata'].get('state') == 'ready'), None)
        receipt = directory / 'still-coordinates.json'
        if cached:
            bucket, path = ref(cached)
            ae._download_gcs_file(ae.GcsRef(bucket, path), receipt)
            if digest(receipt) != cached['metadata']['receipt_sha256']:
                raise ValueError('Saved still coordinate receipt changed')
            saved = json.loads(receipt.read_text('utf-8'))
            if saved['fingerprint'] != key:
                raise ValueError('Still coordinate fingerprint changed')
            regions, receipt_id = saved['regions'], cached['id']
        else:
            speakers = locate_speakers(runner, key, scene, image, postwork['dialogue'], postwork['cast'])
            regions = {'state': 'ready', 'number': scene['number'], 'image_id': scene['source']['id'],
                       'source_sha256': source_hash, 'speakers': speakers}
        if regions.get('image_id') != scene['source']['id'] or regions.get('source_sha256') != source_hash:
            raise ValueError('Still coordinate cache belongs to another source')
        visibility = visible_speakers({'speakers': regions['speakers']}, names)
        for speaker in visibility:
            if speaker['status'] != 'offscreen':
                validate(speaker, source_hash)
        if not cached:
            receipt.write_text(json.dumps({'fingerprint': key, 'regions': regions}, ensure_ascii=False), 'utf-8')
            bucket, path, _ = ae._upload_gcs_file(receipt,
                f'std-projects/{job["project_id"]}/still-coordinates/{scene["source"]["id"]}/{key}.json', 'application/json')
            fresh()
            published = ae._request('POST', base + '/rest/v1/std_project_assets',
                {**headers, 'Prefer': 'return=representation'}, json={
                    'project_id': job['project_id'], 'scene_number': scene['number'], 'asset_type': 'other',
                    'status': 'uploaded', 'file_name': f'still-coordinates-{scene["number"]}.json', 'mime_type': 'application/json',
                    'metadata': {'kind': 'submitted_still_coordinates', 'state': 'ready', 'fingerprint': key,
                                 'gcs_bucket': bucket, 'gcs_path': path, 'receipt_sha256': digest(receipt),
                                 'source_image_id': scene['source']['id'], 'source_sha256': source_hash}}).json()
            if not published:
                raise RuntimeError('Unable to persist actual still coordinates')
            receipt_id = published[0]['id']
    fresh()
    # Reuses reviewed patches when available; generates and reviews only missing ones.
    for speaker in visible_speakers({'speakers': regions['speakers']}, names):
        if speaker['status'] != 'offscreen':
            validate(speaker, source_hash)
    prepare_scene(image, {**regions, 'state': 'ready'}, runner=runner, technical=True)
    fresh()
    return regions, receipt_id
