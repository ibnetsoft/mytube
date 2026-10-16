"""Frozen submission contracts, including required reviewed AE scene artifacts."""
import copy
import hashlib
import json
import re
from ae_scene_review_contract import render_review_matches


def ae_scene_artifact_matches(scene, meta, audio=None):
    prepared = scene.get('ae_scene')
    if not prepared:
        return True
    metadata = prepared.get('metadata') or {}
    result = metadata.get('result') or {}
    review = meta.get('ae_scene_review') or {}
    return (meta.get('kind') == 'ae_scene_output' and meta.get('ae_reviewed') is True
            and meta.get('ae_scene_preparation_id') == prepared.get('id')
            and meta.get('ae_scene_preparation_fingerprint') == metadata.get('fingerprint')
            and meta.get('plan_sha256') == result.get('plan_sha256')
            and meta.get('source_psd_id') == result.get('source_asset_id')
            and meta.get('source_sha256') == result.get('source_sha256')
            and render_review_matches(scene, audio or {}, review, meta.get('render_sha256')))


def validate_required_scene_results(snapshot, outcomes):
    """Required AE production never inherits optional mouth-work fallbacks."""
    rows = list(outcomes.values()) if isinstance(outcomes, dict) else outcomes
    for scene in snapshot.get('scenes') or []:
        if not scene.get('ae_scene'):
            continue
        matches = [row for row in rows if row.get('number') == scene['number']]
        if (len(matches) != 1 or matches[0].get('status') != 'artifact_ready'
                or not matches[0].get('asset_id')
                or not re.fullmatch('[0-9a-f]{64}', str(matches[0].get('render_sha256') or ''))
                or not render_review_matches(scene, snapshot.get('audio') or {},
                    matches[0].get('output_review'), matches[0].get('render_sha256'))):
            raise ValueError(f"Required AE scene {scene['number']} needs rendered-output review")


def sequence_fingerprint(meta):
    rows = []
    for scene in meta['input']['scenes']:
        result = next((row for row in meta.get('results') or [] if row.get('number') == scene['number']), {})
        rows.append([scene['number'], result.get('status') or None,
                     result.get('asset_id') or None, result.get('render_sha256') or None])
    return hashlib.sha256(json.dumps([meta['fingerprint'], rows], ensure_ascii=False,
                                     separators=(',', ':')).encode()).hexdigest()

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
                or meta.get('source_image_id') != (scene.get('image') or {}).get('id')
                or not ae_scene_artifact_matches(scene, meta, snapshot.get('audio'))):
                continue
            result[scene['number']] = {'number':scene['number'],'duration':scene['end']-scene['start'],
                'status':'artifact_ready','asset_id':asset['id'],'render_sha256':meta['render_sha256'],
                'cache_reused':True}
            if scene.get('ae_scene'):
                result[scene['number']]['output_review'] = copy.deepcopy(meta['ae_scene_review'])
            break
    return result

def assembly_only(meta):
    return meta.get('pipeline_version') == 2


def prepared_scene_direction(direction, layered_source, preview_sync):
    """A mouth preview can use its reviewed flat image while PSD direction stays saved."""
    from manga_ae_templates import template_for_scene
    result = copy.deepcopy(direction)
    template = template_for_scene(result)
    exclusions = []
    if preview_sync and template and not layered_source:
        result['ae_effect_plan']['enabled'] = False
        exclusions.append({'template': template, 'reason': 'Layered PSD unavailable; voice-synced mouth preview preserves the approved flat source.'})
    return result, exclusions

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
