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
    roles = [('background', None, None)]
    for index, character in enumerate(cast, 1):
        ref = Path(character.get('reference_file') or '')
        if not ref.is_file() or not str(character.get('placement_prompt') or '').strip():
            raise ValueError('character needs a reference file and explicit scene placement')
        roles.append((f'character-{index:02d}', ref, character))
    for role, reference, character in roles:
        target = output_dir / f'scene-{number:03d}-{role}.png'
        if target.exists():
            raise FileExistsError(f'preserve existing scene plane: {target}')
        if character is None:
            instructions = 'Generate only the complete environment, without people or text. '
            normalized_role = 'background'
        else:
            instructions = ('Generate only this character as a transparent full-canvas PNG, matching the attached character reference. '
                            'Place them exactly as directed: ' + character['placement_prompt'] + '. No background or text. ')
            normalized_role = 'character'
        raw = generator.generate(prompt=instructions + 'Scene direction: ' + prompt,
                                 role=normalized_role, reference=reference,
                                 work_dir=output_dir / '.generated' / f'scene-{number:03d}-{role}')
        _normalize(raw, target, normalized_role)
        files.append(target)
    result = output_dir / f'scene-{number:03d}.png'
    composite_scene(files[0], files[1:], result)
    return {'scene_number': number, 'scene_file': str(result), 'plane_files': [str(p) for p in files],
            'sha256': hashlib.sha256(result.read_bytes()).hexdigest()}
