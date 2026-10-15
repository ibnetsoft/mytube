"""Resolve planned anchors after narration retiming, without changing voice timing."""
from services.scene_audio_anchor import resolve_scene_audio_anchor

def _subtitle_index(cue, subtitles):
    """A saved array index is a hint, never proof of subtitle identity."""
    scene = cue.get('scene_number')
    text = cue.get('subtitle_text')
    subtitle_id = cue.get('subtitle_id')
    def matches(row):
        return (not text or row.get('anchor_text', row.get('text')) == text) and (scene is None or str(row.get('scene_number')) == str(scene))
    if subtitle_id is not None and any(row.get('id') is not None for row in subtitles):
        found = [i for i, row in enumerate(subtitles) if str(row.get('id')) == str(subtitle_id) and matches(row)]
        return found[0] if len(found) == 1 else -1
    if text:
        found = [i for i, row in enumerate(subtitles) if matches(row)]
        return found[0] if len(found) == 1 else -1
    index = cue.get('subtitle_index')
    return index if isinstance(index, int) and 0 <= index < len(subtitles) and matches(subtitles[index]) else -1


def retime_sfx_cues(cues, subtitles, *, strict=False):
    resolved = []
    for cue in cues:
        if cue.get('enabled') is False:
            continue
        item = dict(cue)
        if cue.get('word_boundary') is not None:
            position = resolve_scene_audio_anchor(cue.get('scene_anchor'), subtitles)
            if cue.get('anchor_scope') == 'scene':
                position = resolve_scene_audio_anchor({'scene_number': cue.get('scene_number'), 'source_text': cue.get('anchor_source_text'), 'offset': cue.get('anchor_offset')}, subtitles)
            index = position['index'] if position else _subtitle_index(cue, subtitles)
            if (cue.get('anchor_scope') == 'scene' or cue.get('scene_anchor')) and not position:
                if strict: raise ValueError('Sound effect scene anchor changed or was deleted; review its position')
                continue
            if index < 0:
                if strict: raise ValueError('Sound effect subtitle anchor changed or was deleted; review its position')
                continue
            sub = subtitles[index]
            item['subtitle_index'] = index
            start = float(sub.get('start', sub.get('start_time', 0)))
            end = float(sub.get('end', sub.get('end_time', start)))
            boundary = int(cue['word_boundary'])
            automatic = cue.get('source') == 'codex-sfx-v1' and not cue.get('user_override')
            # Render currently has subtitle-level retiming, not aligned word timestamps.
            item['start'] = position['start'] if position else start if automatic else start + (end-start) * max(0, min(1, boundary / max(1, len(sub.get('text','').split()))))
            item['timing_mode'] = 'subtitle_start' if automatic else 'estimated_word'
        resolved.append(item)
    accepted = [c for c in resolved if c.get('source') != 'codex-sfx-v1' or c.get('user_override')]
    for cue in sorted((c for c in resolved if c not in accepted), key=lambda c: float(c.get('start',0))):
        if all(abs(float(c.get('start',0))-float(cue.get('start',0))) >= 5 for c in accepted):
            accepted.append(cue)
    return sorted(accepted, key=lambda c: float(c.get('start',0)))
