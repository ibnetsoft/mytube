"""Shared content receipts for active web jobs and local media workers."""
import hashlib
import json
import re
import unicodedata


def speech_text(value):
    return re.sub(r'\s+', '', unicodedata.normalize('NFKC', str(value or '')))


def _numbers(value):
    if isinstance(value, float) and value.is_integer():
        return int(value)
    if isinstance(value, dict):
        return {k: _numbers(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_numbers(v) for v in value]
    return value


def content_hash(value):
    encoded = value if isinstance(value, str) else json.dumps(_numbers(value), ensure_ascii=False, separators=(',', ':'), allow_nan=False)
    return hashlib.sha256(encoded.encode('utf-8')).hexdigest()


def project_identity(project):
    payload = project.get('project_payload') or {}
    rows = payload.get('subtitles') or []
    script = payload.get('script') or ''.join(r.get('text') or '' for r in rows)
    if not script:
        script = ''.join(s.get('scene_text') or s.get('narration') or s.get('text') or '' for s in (payload.get('structure') or {}).get('scenes') or [])
    sha = content_hash(speech_text(script))
    return {'schema_version': 1, 'project_id': str(project['id']), 'topic_queue_id': int(project['topic_queue_id']),
            'script_revision': 'sha256:' + sha, 'script_sha256': sha,
            'subtitle_text_sha256': content_hash(''.join(speech_text(r.get('text')) for r in rows))}


def visual_hash(scene, kind):
    return content_hash({'image_prompt': str(scene.get('image_prompt') or scene.get('prompt') or ''),
                         'video_prompt': str(scene.get('video_prompt') or '') if kind == 'video' else ''})


def timeline_rows(rows):
    def time(row, prefix):
        for key in (prefix + '_num', prefix + '_time', prefix):
            if row.get(key) is not None:
                return float(row[key])
        raise ValueError('CONTENT_IDENTITY_MISMATCH: missing subtitle time')
    return [{'text': speech_text(row.get('text')), 'start': time(row, 'start'), 'end': time(row, 'end'),
             'voice_id': str(row.get('voice_id') or row.get('voiceId') or '')} for row in rows]


def asset_identity(project, kind, scene, *, parents=(), audio_id=None, job_id=None):
    number = scene.get('scene_number')
    return {**project_identity(project), 'asset_type': kind, 'scene_id': scene.get('id'), 'scene_number': number,
            'scene_key': f"{project['id']}:{number}", 'visual_sha256': visual_hash(scene, kind),
            'audio_asset_id': audio_id, 'timeline_sha256': None, 'parent_asset_ids': list(parents),
            'generation_job_id': job_id}


def mouth_output_identity(job, scene):
    # Carry the submitted generation snapshot, never the project's current revision.
    identity = (job.get('metadata') or {}).get('content_identity')
    if not identity:
        return None  # Preserve legacy outputs without inventing birth provenance.
    return {**identity, 'asset_type': 'video', 'scene_number': scene['number'],
            'scene_key': f"{job['project_id']}:{scene['number']}", 'generation_job_id': job['id'],
            'parent_asset_ids': [value for value in [(scene.get('image') or {}).get('id'),
                (scene.get('original_video') or {}).get('id'), (job['metadata']['input'].get('audio') or {}).get('id')] if value]}


def validate_render_identity(config, queue_metadata):
    identity = config.get('content_identity')
    if not identity:
        return  # Already registered legacy renders remain unchanged.
    if identity != queue_metadata.get('content_identity'):
        raise ValueError('CONTENT_IDENTITY_MISMATCH: render config and queue revision differ')
    if str(config.get('std_web_project_id')) != identity.get('project_id') or int(queue_metadata.get('topic_queue_id') or 0) != identity.get('topic_queue_id'):
        raise ValueError('CONTENT_IDENTITY_MISMATCH: render project/topic differs')
    files = (config.get('asset_manifest') or {}).get('files') or []
    audio = [f for f in files if f.get('asset_type') == 'audio']
    if len(audio) != 1:
        raise ValueError('CONTENT_IDENTITY_MISMATCH: exactly one narration file is required')
    receipt = audio[0].get('content_identity') or {}
    if receipt.get('project_id') != identity['project_id'] or receipt.get('script_sha256') != identity['script_sha256']:
        raise ValueError('CONTENT_IDENTITY_MISMATCH: narration project/revision differs')
    if config.get('worker_tts'):
        raise ValueError('CONTENT_IDENTITY_MISMATCH: finalized narration cannot be regenerated during render')
    if receipt.get('timeline_sha256'):
        if content_hash(timeline_rows(config.get('subtitles') or [])) != receipt['timeline_sha256']:
            raise ValueError('CONTENT_IDENTITY_MISMATCH: captions differ from recorded narration')
        if abs(float(config.get('audio_duration') or 0) - float(receipt.get('duration_seconds') or 0)) > .15:
            raise ValueError('CONTENT_IDENTITY_MISMATCH: render duration differs from recorded narration')
    for item in files:
        if item.get('asset_type') not in ('image', 'video'):
            continue
        receipt = item.get('content_identity') or {}
        if receipt.get('scene_number') != item.get('scene_number'):
            raise ValueError('CONTENT_IDENTITY_MISMATCH: render scene differs')
        source = receipt.get('source_content_identity') or {}
        if source and (source.get('project_id') != identity['project_id'] or source.get('topic_queue_id') != identity['topic_queue_id']):
            raise ValueError('CONTENT_IDENTITY_MISMATCH: source asset project/topic differs')
        if source.get('audio_asset_id') and source['audio_asset_id'] != audio[0]['content_identity'].get('asset_id'):
            raise ValueError('CONTENT_IDENTITY_MISMATCH: derived video uses another narration')
