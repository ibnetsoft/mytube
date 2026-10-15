"""Version-two submission contracts; no model approval or image generation."""
import copy
import re

def ready_scene_artifacts(snapshot, assets, fingerprint):
    result = {}
    for scene in snapshot['scenes']:
        for asset in assets:
            meta = asset.get('metadata') or {}
            if (asset.get('asset_type') != 'video' or meta.get('kind') == 'mouth_preview'
                or meta.get('timing_mode') == 'preview_cycle' or meta.get('voice_synced') is False
                or asset.get('status') not in ('uploaded','assigned') or asset.get('scene_number') != scene['number']
                or meta.get('artifact_ready') is not True or meta.get('ae_mouth_fingerprint') != fingerprint
                or meta.get('source_audio_id') != snapshot['audio']['id'] or not meta.get('timing_locked')
                or not re.fullmatch('[0-9a-f]{64}', str(meta.get('render_sha256') or ''))
                or abs(float(meta.get('duration_seconds') or 0)-(scene['end']-scene['start'])) > .12
                or meta.get('source_image_id') != (scene.get('image') or {}).get('id')):
                continue
            result[scene['number']] = {'number':scene['number'],'duration':scene['end']-scene['start'],
                'status':'artifact_ready','asset_id':asset['id'],'render_sha256':meta['render_sha256'],
                'cache_reused':True}
            break
    return result

def assembly_only(meta):
    return meta.get('pipeline_version') == 2

def validate_layers(image, speaker):
    from prepared_mouth_layers import reuse_prepared
    if not reuse_prepared(image, speaker):
        raise ValueError('Prepared mouth layers unavailable; keep selected original')
    return speaker

def render_prepared_scene(ae, specification, technical):
    """The AE adapter closes its owned process on failure; retry the same recipe once."""
    try:
        return ae._render_job(specification, keep_workdir=True)
    except Exception as exc:
        if not technical or not any(marker in str(exc) for marker in ('After Effects', 'AfterFX', 'aerender', 'AE render')):
            raise
        return ae._render_job(specification, keep_workdir=True)

def recorded_rows(snapshot):
    rows = copy.deepcopy(snapshot.get('subtitles') or [])
    for row in rows:
        if row.get('kind') not in ('dialogue', 'narration'):
            row['kind'] = 'narration'
        if row['kind'] == 'dialogue' and not row.get('speaker'):
            raise ValueError('Saved dialogue requires a selected speaker')
    return rows

def stage_record(ae, base, headers, meta, number, state, artifact=None, error=None):
    if not assembly_only(meta) or not meta.get('pipeline_run_id'):
        return
    receipt = ae._request('POST', base + '/rest/v1/rpc/record_std_pipeline_stage', headers,
        json={'p_run_id': meta['pipeline_run_id'], 'p_token': meta['worker_token'],
              'p_number': number, 'p_state': state, 'p_artifact': artifact, 'p_error': error}).json()
    if receipt is not True: raise RuntimeError('Stage lease no longer belongs to this worker')
