"""Generate scene planes first and compose the scene from those original planes."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from worker.layered_scene_composite import composite_scene
from worker.manga_layer_generation import NativeCodexLayerGenerator, _normalize


def generate_scene_planes(scene: dict[str, Any], output_dir: Path, *, generator=None) -> dict[str, Any]:
    """Create a background and one transparent plane per named character.

    Each character item provides key, reference_file and placement_prompt. Existing
    files are never replaced; a generated scene can be reused after interruption.
    """
    number = scene.get('scene_number')
    prompt = str(scene.get('image_prompt') or '').strip()
    cast = scene.get('characters', [])
    if type(number) is not int or number < 1 or not prompt or not isinstance(cast, list):
        raise ValueError('scene_number, image_prompt and characters are required')
    keys = [c.get('key') for c in cast if isinstance(c, dict)]
    if len(keys) != len(cast) or len(set(keys)) != len(keys) or any(not isinstance(k, str) or not k for k in keys):
        raise ValueError('each character needs a unique key')
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    generator = generator or NativeCodexLayerGenerator()
    files = []
    receipt_path = output_dir / f'scene-{number:03d}-planes.json'
    receipt = json.loads(receipt_path.read_text(encoding='utf-8')) if receipt_path.exists() else {}
    source_fingerprints = {str(c.get('key')): hashlib.sha256(Path(c['reference_file']).read_bytes()).hexdigest()
                           for c in cast if isinstance(c, dict) and c.get('reference_file') and Path(c['reference_file']).is_file()}
    fingerprint = hashlib.sha256(json.dumps({'scene': scene, 'references': source_fingerprints}, sort_keys=True, ensure_ascii=False).encode('utf-8')).hexdigest()
    if receipt and receipt.get('fingerprint') != fingerprint:
        raise ValueError('scene directions changed; preserve the existing planes')
    receipt = receipt or {'fingerprint': fingerprint, 'files': {}, 'character_keys': {}}
    roles = [('background', None, None)]
    for index, character in enumerate(cast, 1):
        reference_file = character.get('reference_file')
        ref = Path(reference_file) if reference_file else None
        if (ref is not None and not ref.is_file()) or (ref is None and character.get('one_scene_only') is not True) or not str(character.get('placement_prompt') or '').strip():
            raise ValueError('character needs an existing reference or an explicitly one-scene role, plus scene placement')
        roles.append((f'character-{index:02d}', ref, character))
    for role, reference, character in roles:
        target = output_dir / f'scene-{number:03d}-{role}.png'
        if target.exists():
            expected = receipt['files'].get(role)
            if not expected or hashlib.sha256(target.read_bytes()).hexdigest() != expected:
                raise FileExistsError(f'preserve unrecognized or changed scene plane: {target}')
            files.append(target)
            continue
        if character is None:
            instructions = 'Generate only the complete environment, without people or text, as a full 16:9 landscape canvas. '
            normalized_role = 'background'
        else:
            identity = 'matching the attached character reference' if reference else 'using this one-scene character description'
            instructions = ('Generate only this character on a transparent full 16:9 landscape canvas, ' + identity + '. '
                            'Place them exactly as directed: ' + character['placement_prompt'] + '. No background or text. ')
            normalized_role = 'character'
        raw = generator.generate(prompt=instructions + 'Scene direction: ' + prompt,
                                 role=normalized_role, reference=reference,
                                 work_dir=output_dir / '.generated' / f'scene-{number:03d}-{role}')
        temporary = target.with_suffix('.png.tmp')
        _normalize(raw, temporary, normalized_role)
        temporary.replace(target)
        receipt['files'][role] = hashlib.sha256(target.read_bytes()).hexdigest()
        if character is not None:
            receipt.setdefault('character_keys', {})[role] = character['key']
        receipt_path.write_text(json.dumps(receipt, ensure_ascii=False, indent=2), encoding='utf-8')
        files.append(target)
    result = output_dir / f'scene-{number:03d}.png'
    if result.exists():
        expected = receipt.get('scene_sha256')
        if not expected or hashlib.sha256(result.read_bytes()).hexdigest() != expected:
            raise FileExistsError(f'preserve unrecognized or changed scene image: {result}')
    else:
        composite_scene(files[0], files[1:], result)
        receipt['scene_sha256'] = hashlib.sha256(result.read_bytes()).hexdigest()
        receipt_path.write_text(json.dumps(receipt, ensure_ascii=False, indent=2), encoding='utf-8')
    return {'scene_number': number, 'scene_file': str(result), 'plane_files': [str(p) for p in files],
            'sha256': hashlib.sha256(result.read_bytes()).hexdigest()}


def generate_manifest_scenes(manifest: dict[str, Any], output_dir: Path, *, generator=None, max_workers: int = 1) -> list[dict[str, Any]]:
    """Generate scene composites in the explicit range using saved cast references."""
    from worker.effect_scene_scope import normalize_scope, contains
    scope = normalize_scope(manifest.get('effect_scene_range'))
    if scope is None:
        raise ValueError('manifest is missing its explicit effect scene range')
    scenes, cast, references = manifest.get('scene_specs'), manifest.get('scene_cast'), manifest.get('character_references')
    if not isinstance(scenes, list) or not isinstance(cast, list) or not isinstance(references, list):
        raise ValueError('manifest must include scenes, cast and character references')
    by_scene = {item['scene_number']: item['characters'] for item in cast
                if isinstance(item, dict) and type(item.get('scene_number')) is int and isinstance(item.get('characters'), list)}
    appearance_counts = {}
    for names in by_scene.values():
        for name in set(names):
            key = str(name).strip().casefold()
            appearance_counts[key] = appearance_counts.get(key, 0) + 1
    by_name = {}
    for reference in references:
        for name in [reference.get('name'), reference.get('character_key'), *(reference.get('aliases') or [])]:
            if name:
                by_name[str(name).strip().casefold()] = reference
    jobs = []
    for scene in scenes:
        number = scene.get('scene_number')
        if type(number) is not int or not contains(scope, number):
            continue
        if number not in by_scene:
            raise ValueError(f'scene {number} is missing its cast')
        characters = []
        for name in by_scene[number]:
            reference = by_name.get(str(name).strip().casefold())
            if not reference or not reference.get('local_file') or not reference.get('character_key'):
                if appearance_counts.get(str(name).strip().casefold()) != 1:
                    raise ValueError(f'scene {number}: missing reference for recurring character {name}')
                characters.append({'key': f'one-scene-{number}-{len(characters)+1}', 'one_scene_only': True,
                                   'placement_prompt': f"{name}; follow the character description, position and scale in the scene direction"})
            else:
                characters.append({'key': reference['character_key'], 'reference_file': reference['local_file'],
                                   'placement_prompt': f"{name}; follow the character position and scale in the scene direction"})
        jobs.append({'scene_number': number, 'image_prompt': scene.get('generation_image_prompt') or scene.get('image_prompt'),
                     'characters': characters})
    if max_workers < 1 or max_workers > 4:
        raise ValueError('max_workers must be between 1 and 4')
    if max_workers == 1:
        return [generate_scene_planes(job, output_dir, generator=generator) for job in jobs]
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        return list(pool.map(lambda job: generate_scene_planes(job, output_dir, generator=generator), jobs))
