"""Bound script-time mouth preparation; never spend the cap per image batch."""
import json
from pathlib import Path

SETTINGS = Path(__file__).resolve().parents[1] / 'output/codex-local-console/mouth-policy.json'
DEFAULT = {'enabled': True, 'start_scene': 19, 'max_dialogue_scenes': 10}


def normalize(value):
    value = value if isinstance(value, dict) else {}
    result = {**DEFAULT, **{k: value[k] for k in DEFAULT if k in value}}
    if not isinstance(result['enabled'], bool):
        raise ValueError('enabled must be boolean')
    for key, minimum, maximum in [('start_scene', 1, 10000), ('max_dialogue_scenes', 0, 1000)]:
        v = result[key]
        if isinstance(v, bool) or not isinstance(v, int) or not minimum <= v <= maximum:
            raise ValueError(f'{key} must be an integer between {minimum} and {maximum}')
    return result


def load_policy():
    try:
        return normalize(json.loads(SETTINGS.read_text(encoding='utf8')))
    except FileNotFoundError:
        return dict(DEFAULT)


def selected_scenes(structure, policy):
    policy = normalize(policy)
    if not policy['enabled']:
        return []
    known = {int(s.get('scene_number') or s.get('scene_order') or i + 1)
             for i, s in enumerate(structure.get('scenes') or [])}
    numbers = set()
    for row in (structure.get('dialogue_annotations') or {}).get('scenes', []):
        number = int(row.get('scene_number') or 0)
        if number in known and number >= policy['start_scene'] and any(
            str(s.get('text') or '').strip() and str(s.get('speaker') or '').strip()
            and s.get('status') == 'confirmed' for s in row.get('spans', [])):
            numbers.add(number)
    return sorted(numbers)[:policy['max_dialogue_scenes']]
