"""Map subtitle text spans to measured speech times, without stretching speech."""
import math


def validate_alignment(text, alignment):
    if not isinstance(alignment, dict):
        raise ValueError('Speech character timestamps are missing')
    chars = alignment.get('characters', [])
    starts = alignment.get('character_start_times_seconds', [])
    ends = alignment.get('character_end_times_seconds', [])
    if ''.join(chars) != text or not chars or len(chars) != len(starts) or len(chars) != len(ends):
        raise ValueError('Speech timestamps do not match the synthesized transcript')
    previous = 0.0
    for start, end in zip(starts, ends):
        if not all(isinstance(v, (int, float)) and math.isfinite(v) for v in (start, end)):
            raise ValueError('Invalid speech timestamp')
        if start < previous or end < start:
            raise ValueError('Speech timestamps are out of order')
        previous = start
    return alignment


def aligned_span(text, alignment, start, end, offset=0.0, speed_ratio=1.0):
    validate_alignment(text, alignment)
    indices = [i for i in range(max(0, start), min(len(text), end)) if not text[i].isspace()]
    if not indices:
        return None
    return (offset + alignment['character_start_times_seconds'][indices[0]] / speed_ratio,
            offset + alignment['character_end_times_seconds'][indices[-1]] / speed_ratio)
