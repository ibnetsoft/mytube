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
