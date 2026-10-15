"""Short AE preview made once beside the pose art, before finalized speech."""
import copy
import json
from pathlib import Path

def prepare_preview(topic_id, number, image, geometry, preparation):
    if preparation.get('state') != 'ready':
        return {'state': 'not_required'}
    import ae_highlight_worker as ae
    from ae_mouth import digest, POSES
    from prepared_mouth_layers import ROOT, reuse_prepared
    speakers = []
    for index, original in enumerate(geometry.get('speakers', [])):
        if original.get('status') != 'visible': continue
        row = copy.deepcopy(original)
        if not reuse_prepared(image, row):
            entry = next((e for e in preparation.get('entries', []) if e['speaker'] == row['speaker']), None)
            key = entry['key'] if entry else (preparation['keys'][index] if index < len(preparation['keys']) else None)
            if not key: continue
            directory = ROOT / key
            receipt_file = directory / 'artifact-ready.json'
            if not receipt_file.exists(): receipt_file = directory / 'reviewed.json'
            receipt = json.loads(receipt_file.read_text(encoding='utf8'))
            if receipt['source'] != digest(image) or receipt['key'] != key: raise ValueError('Preview source changed')
            row['layers'] = {pose: str(directory / f'{pose}.png') for pose in POSES}
            if any(digest(Path(row['layers'][pose])) != receipt['hashes'][pose] for pose in POSES): raise ValueError('Preview pose bytes changed')
            row['mouth_box'], row['coverage_version'] = receipt['mouth_box'], 2
        row['cues'] = [{'at_seconds': i / 6, 'pose': POSES[i % len(POSES)]} for i in range(18)]
        speakers.append(row)
    if not speakers: return {'state': 'not_required'}
    key = ae.fingerprint({'version': 1, 'source': digest(image), 'prepared': preparation['keys']})
    receipt_file = ROOT / 'previews' / key / 'published.json'
    if receipt_file.exists(): return json.loads(receipt_file.read_text(encoding='utf8'))
    scene = {'scene_number': number, 'duration_seconds': 3,
        'ae_motion_plan': {'enabled': True, 'preset': 'subtle_dialogue', 'vfx': [], 'intensity': 0,
            'motion': {'push': 0, 'drift_x': 0, 'drift_y': 0, 'shake': 0}},
        'ae_mouth_runtime': {'enabled': True, 'speakers': speakers, 'blinks': []}}
    spec = ae.SceneJob(topic_id=topic_id, topic_title='Mouth preview before voice sync', structure={'scenes': [scene]},
        scene_index=0, scene=scene, scene_number=number, plan_kind='motion', preset='subtle_dialogue',
        duration_seconds=3, source=ae.GcsRef('__local__', str(image.resolve())), source_type='project',
        project_payload={'ae_scene_delivery': 'local'})
    rendered = ae._render_job(spec, keep_workdir=True)
    video = Path(rendered['local_path'])
    bucket, path, url = ae._upload_gcs_file(video, f'topics/{topic_id}/mouth-previews/{key}.mp4', 'video/mp4')
    receipt = {'state': 'ready', 'kind': 'mouth_preview', 'timing_mode': 'preview_cycle',
        'voice_synced': False, 'duration_seconds': 3, 'gcs_bucket': bucket, 'gcs_path': path,
        'url': url, 'sha256': digest(video), 'source_sha256': digest(image), 'prepared_keys': preparation['keys']}
    receipt_file.parent.mkdir(parents=True, exist_ok=True)
    receipt_file.write_text(json.dumps(receipt), encoding='utf8')
    return receipt
