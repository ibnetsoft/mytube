"""Analyze final published stills with local Codex; checkpoint every scene."""
import copy
import dataclasses
import hashlib
import json
import uuid
from pathlib import Path
from datetime import datetime, timezone

REFERENCE_ROOT = Path(__file__).resolve().parents[1] / "output" / "codex-local-console" / "generated-speakers"


def cast_for(structure):
    return {'main': structure.get('main_character') or {},
            'supporting': structure.get('supporting_characters') or [],
            'scene_cast': structure.get('scene_cast') or []}


def analyze_scene(structure, scene, image, bucket, path, previous=None, runner=None):
    from ae_mouth import locate_speakers
    number = int(scene.get('scene_number') or scene.get('scene_order'))
    source = str(scene.get('scene_text') or scene.get('narration') or '')
    image_hash = hashlib.sha256(image.read_bytes()).hexdigest()
    cast = cast_for(structure)
    annotation = next((r for r in (structure.get('dialogue_annotations') or {}).get('scenes', [])
                       if r.get('scene_number') == number), None)
    identity = {'source_sha256': image_hash, 'source_bucket': bucket, 'source_path': path,
                'cast': cast, 'annotation': annotation, 'text': source}
    fingerprint = hashlib.sha256(json.dumps(identity, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    if previous and previous.get('fingerprint') == fingerprint and previous.get('state') in ('ready', 'not_required'):
        return previous
    result = {'version': 1, 'source': 'local-codex-image-publish', 'number': number,
              'fingerprint': fingerprint, 'cast': cast, 'source_bucket': bucket, 'source_path': path,
              'source_sha256': image_hash, 'speakers': [], 'updated_at': datetime.now(timezone.utc).isoformat()}
    try:
        if not annotation or annotation.get('source_sha256') != hashlib.sha256(source.encode()).hexdigest():
            raise ValueError('Current script dialogue annotations are missing or stale')
        spans = annotation.get('spans')
        if not isinstance(spans, list):
            raise ValueError('Dialogue annotations need review')
        if any(s.get('status') != 'confirmed' or not str(s.get('speaker') or '').strip() for s in spans):
            raise ValueError('Dialogue speaker assignment needs review')
        if not spans:
            return {**result, 'state': 'not_required'}
        rows = [{'kind': 'dialogue', 'speaker': s['speaker'], 'text': s['text']} for s in spans]
        if runner is None:
            from codex_content_runner import CodexStagedContentRunner
            runner = CodexStagedContentRunner()
            runner.config = dataclasses.replace(runner.config, timeout_seconds=min(180, runner.config.timeout_seconds))
        # The Codex runner only permits attachments within its local workspace.
        reference = REFERENCE_ROOT / fingerprint / 'source.png'
        reference.parent.mkdir(parents=True, exist_ok=True)
        pixels = image.read_bytes()
        if hashlib.sha256(pixels).hexdigest() != image_hash:
            raise ValueError('Scene image changed before coordinate analysis')
        reference.write_bytes(pixels)
        speakers = locate_speakers(runner, 'image-coordinates-' + fingerprint + '-' + uuid.uuid4().hex,
                                   {'text': source}, reference, rows, cast)
        if any(s['status'] == 'visible' and not s.get('face_box') for s in speakers):
            raise ValueError('Face bounds are missing')
        return {**result, 'state': 'ready', 'speakers': speakers}
    except Exception as exc:
        return {**result, 'state': 'needs_review', 'error': str(exc)[:500]}


def analyze_published_scenes(topic_id, structure, scenes, images_dir, base_url, headers, publisher):
    """Images are already committed. A later failure cannot erase earlier results.

    The same scene-asset CAS as image publication protects concurrent replacements.
    Failed DB writes stop publication, so retrying the command can recover them.
    """
    for number, scene in sorted(scenes.items()):
        if number < 19:
            continue  # Uploaded clips need their own reference frames.
        asset = scene['metadata']['cowork_image_asset']
        previous = asset.get('speaker_geometry')
        receipt_path = images_dir / f'scene-{number:03d}-speaker-coordinates.json'
        if receipt_path.exists():
            try:
                cached = json.loads(receipt_path.read_text(encoding='utf-8'))
                if cached.get('state') in ('ready', 'not_required'):
                    previous = cached
            except (ValueError, OSError):
                pass
        result = analyze_scene(structure, scene, images_dir / f'scene-{number:03d}.png',
                               asset['gcs_bucket'], asset['gcs_path'], previous)
        temp = receipt_path.with_suffix('.tmp')
        temp.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
        temp.replace(receipt_path)
        expected = publisher._scene_asset_snapshot(scene)
        updated = copy.deepcopy(scene)
        updated['metadata']['cowork_image_asset']['speaker_geometry'] = result
        publisher._patch_topic_scene_assets(topic_id, [{
            'scene_number': number,
            'expected_source': publisher._publish_source_snapshot(scene, number),
            'expected_assets': expected,
            'asset_patch': publisher._scene_asset_patch(updated),
        }], base_url, headers)
        scene.clear()
        scene.update(updated)
        print(f'Scene {number}: speaker coordinates {result["state"]}', flush=True)
