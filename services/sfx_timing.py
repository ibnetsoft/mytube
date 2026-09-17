"""Resolve planned anchors after narration retiming, without changing voice timing."""
def retime_sfx_cues(cues, subtitles):
    resolved = []
    for cue in cues:
        if cue.get('enabled') is False:
            continue
        item = dict(cue)
        if cue.get('word_boundary') is not None:
            index = cue.get('subtitle_index')
            if not isinstance(index, int) or not 0 <= index < len(subtitles):
                continue
            sub = subtitles[index]
            start = float(sub.get('start', sub.get('start_time', 0)))
            end = float(sub.get('end', sub.get('end_time', start)))
            boundary = int(cue['word_boundary'])
            automatic = cue.get('source') == 'codex-sfx-v1' and not cue.get('user_override')
            # Render currently has subtitle-level retiming, not aligned word timestamps.
            item['start'] = start if automatic else start + (end-start) * max(0, min(1, boundary / max(1, len(sub.get('text','').split()))))
            item['timing_mode'] = 'subtitle_start' if automatic else 'estimated_word'
        resolved.append(item)
    accepted = [c for c in resolved if c.get('source') != 'codex-sfx-v1' or c.get('user_override')]
    for cue in sorted((c for c in resolved if c not in accepted), key=lambda c: float(c.get('start',0))):
        if all(abs(float(c.get('start',0))-float(cue.get('start',0))) >= 5 for c in accepted):
            accepted.append(cue)
    return sorted(accepted, key=lambda c: float(c.get('start',0)))
