"""Resolve the web's scene/text anchors against the final narration timeline."""
import math


def _text(row):
    return str(row.get('anchor_text', row.get('text', '')) or '')


def _compact(text):
    return ''.join(str(text or '').split())


def _position(row, index, offset, length):
    start = float(row.get('start_num', row.get('start', row.get('start_time', 0))))
    end = float(row.get('end_num', row.get('end', row.get('end_time', start))))
    if not math.isfinite(start) or not math.isfinite(end) or end < start:
        return None
    if offset < 0 or offset > length:
        return None
    words = _text(row).split()
    consumed, boundary = 0, 0
    while boundary < len(words) and consumed < offset:
        consumed += len(_compact(words[boundary]))
        boundary += 1
    fraction = boundary / max(1, len(words)) if consumed == offset else offset / max(1, length)
    return {'index': index, 'start': start + (end - start) * fraction}


def resolve_scene_audio_anchor(anchor, rows):
    if not isinstance(anchor, dict):
        return None
    offset = anchor.get('offset')
    if not isinstance(offset, (int, float)) or not math.isfinite(offset) or offset < 0 or int(offset) != offset:
        return None
    scene = [(i, row) for i, row in enumerate(rows) if str(row.get('scene_number')) == str(anchor.get('scene_number'))]
    direct = [(i, row) for i, row in scene if anchor.get('subtitle_id') is not None
              and str(row.get('id')) == str(anchor['subtitle_id']) and _text(row) == anchor.get('subtitle_text')]
    local = anchor.get('subtitle_offset')
    if len(direct) == 1 and isinstance(local, (int, float)) and math.isfinite(local) and local >= 0 and int(local) == local:
        i, row = direct[0]
        if local <= len(_compact(_text(row))):
            return _position(row, i, local, len(_compact(_text(row))))
    if not scene or ''.join(_compact(_text(row)) for _, row in scene) != _compact(anchor.get('source_text')):
        return None
    for position, (index, row) in enumerate(scene):
        length = len(_compact(_text(row)))
        if offset < length or position == len(scene) - 1:
            return _position(row, index, offset, length) if offset <= length else None
        offset -= length
    return None
