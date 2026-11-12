"""Resolve scene-bound stored 2D patches into a verified local render manifest."""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from PIL import Image

from ae_media_utils import ref
from motion2d_mvp import render, sha256

ROLES = ('mouth_closed', 'mouth_half', 'mouth_open', 'blink', 'hair')


def _sha(value):
    return isinstance(value, str) and len(value) == 64 and all(c in '0123456789abcdef' for c in value)


def prepare_and_render(snapshot: dict, directory: Path, download, rhubarb: str) -> dict:
    """Download verified assets once and render. The caller owns the job lease.

    download(bucket, key, path) must download only owned storage objects. The
    snapshot must be selected by the authenticated server, never from a client.
    """
    if snapshot.get('version') != 1 or not isinstance(snapshot.get('project_id'), str):
        raise ValueError('Invalid motion job snapshot')
    project_id, scene = snapshot['project_id'], snapshot['scene']
    if type(scene) is not int or scene < 1:
        raise ValueError('Invalid scene number')
    image, audio, patches = snapshot['image'], snapshot['audio'], snapshot['patches']
    source_sha, audio_sha = snapshot['image_sha256'], snapshot['audio_sha256']
    if not _sha(source_sha) or not _sha(audio_sha):
        raise ValueError('Image and audio SHA-256 are required')
    if image.get('project_id') != project_id or image.get('scene_number') != scene or image.get('asset_type') != 'image' or image.get('status') not in ('uploaded', 'assigned'):
        raise ValueError('Source image ownership changed')
    if audio.get('project_id') != project_id or audio.get('asset_type') != 'audio' or audio.get('status') not in ('uploaded', 'assigned') or (audio.get('metadata') or {}).get('sha256') != audio_sha:
        raise ValueError('Narration ownership or fingerprint changed')
    if not isinstance(patches, dict) or set(patches) != set(ROLES):
        raise ValueError('All five scene patches are required')
    directory.mkdir(parents=True, exist_ok=True)
    def acquire(asset, filename, expected):
        if not _sha(expected): raise ValueError('Asset checksum missing')
        bucket, key = ref(asset)
        target = directory / filename
        if target.exists():
            if sha256(target) != expected: raise ValueError('Cached asset checksum mismatch')
        else:
            download(bucket, key, target)
            if sha256(target) != expected: raise ValueError('Downloaded asset checksum mismatch')
        return target
    original = acquire(image, 'original.png', source_sha)
    voice = acquire(audio, 'audio.bin', audio_sha)
    paths = {}
    for role in ROLES:
        asset = patches[role]; meta = asset.get('metadata') or {}
        if (asset.get('project_id') != project_id or asset.get('scene_number') != scene or asset.get('status') not in ('uploaded', 'assigned') or meta.get('kind') != 'motion2d_patch' or meta.get('role') != role or meta.get('imageId') != image.get('id') or meta.get('imageSha256') != source_sha):
            raise ValueError('A saved patch is not bound to this scene and source')
        paths[role] = acquire(asset, role + '.png', meta.get('sha256'))
    background = snapshot.get('background')
    if not background:
        raise ValueError('A repaired background is required behind moving hair')
    meta = background.get('metadata') or {}
    if (background.get('project_id') != project_id or background.get('scene_number') != scene or background.get('status') not in ('uploaded', 'assigned') or meta.get('kind') != 'region_layer_upload' or meta.get('role') != 'background' or meta.get('imageId') != image.get('id') or meta.get('imageSha256') != source_sha):
        raise ValueError('Repaired background does not match the current scene source')
    base = acquire(background, 'background.png', meta.get('sha256'))
    with Image.open(original) as original_image:
        original_size = original_image.size
    ratio = min(1., 1920 / max(original_size))
    render_size = tuple(max(2, int(n * ratio) // 2 * 2) for n in original_size)
    with Image.open(base) as repaired:
        if repaired.size != render_size:
            raise ValueError('Repaired background size does not match the scene canvas')
    for role, path in paths.items():
        with Image.open(path) as image_file:
            if image_file.size != original_size or image_file.mode != 'RGBA':
                raise ValueError('Saved patch canvas no longer matches the source')
            if image_file.size != render_size:
                resized = directory / ('render-' + role + '.png')
                image_file.resize(render_size, Image.Resampling.LANCZOS).save(resized)
                paths[role] = resized
    start = float(snapshot.get('audio_start', 0))
    if not math.isfinite(start) or start < 0: raise ValueError('Invalid narration start')
    manifest = {'source':str(base.resolve()),'audio':str(voice.resolve()),'audio_start':start,
        'mouths':{'closed':str(paths['mouth_closed'].resolve()),'half':str(paths['mouth_half'].resolve()),'open':str(paths['mouth_open'].resolve())},
        'rhubarb_executable':rhubarb,'blink':{'sprite':str(paths['blink'].resolve()),'start':2.,'end':2.17},
        'hair':{'sprite':str(paths['hair'].resolve()),'anchor_y':.2,'amplitude_px':12,'period':2.}}
    manifest_file = directory / 'manifest.json'
    manifest_file.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
    output = directory / 'motion2d.mp4'
    result = render(manifest_file, output)
    result.update({'original_sha256':sha256(original),'audio_asset_id':audio['id'],'image_asset_id':image['id'],
                   'patch_assets':{role:patches[role]['id'] for role in ROLES},'background_asset_id':background['id'],
                   'output':str(output),'snapshot_sha256':hashlib.sha256(json.dumps(snapshot,sort_keys=True,ensure_ascii=False,separators=(',',':')).encode()).hexdigest()})
    return result
