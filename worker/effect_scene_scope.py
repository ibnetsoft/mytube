"""Scene range policy for newly-created layered productions.

The absence of this policy means legacy productions keep their original rules.
"""
from typing import Any


def normalize_scope(value: Any) -> dict[str, int] | None:
    if value is None:
        return None
    if not isinstance(value, dict):
        raise ValueError('effect scene range must be an object')
    start, end = value.get('start'), value.get('end')
    if type(start) is not int or type(end) is not int or not 1 <= start <= end <= 999:
        raise ValueError('effect scene range requires 1 <= start <= end <= 999')
    return {'start': start, 'end': end}


def contains(scope: dict[str, int] | None, number: int) -> bool:
    return scope is None or scope['start'] <= number <= scope['end']


def chapter_scope(scope: dict[str, int] | None, offset: int) -> dict[str, int] | None:
    """Return local coordinates, retaining an empty range for later chapters."""
    if scope is None:
        return None
    return {'start': max(1, scope['start'] - offset), 'end': max(0, scope['end'] - offset)}


def validate_directions(scope: dict[str, int] | None, scenes: list, directions: list, *, offset: int = 0) -> list:
    """Fail closed if the director adds layered effects outside the selected range."""
    if scope is None:
        return directions
    for index, (scene, direction) in enumerate(zip(scenes, directions), 1):
        number = int(scene.get('scene_number') or scene.get('scene_order') or index)
        if contains(scope, number + offset):
            continue
        operations = set(direction.get('ae_operations') or [])
        blink = direction.get('eye_blink_plan') or {}
        if (operations - {'hold', 'camera_move', 'transition'} or
                direction.get('requires_layered_assets') or direction.get('required_layers') or
                direction.get('additional_keyframes') or blink.get('enabled')):
            raise ValueError(f'scene {number}: effects or layers outside selected scene range')
    return directions
