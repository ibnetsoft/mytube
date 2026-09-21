"""Keep subtitle display boundaries out of speech synthesis requests."""
import re


def sentence_segments(raw_segments, subtitles, target_chars=350, max_chars=1200):
    turns = []
    for raw in raw_segments:
        voice = str(raw.get('voice_id') or '').strip()
        direction = str(raw.get('direction') or '') if voice.startswith('gemini:') else ''
        indices = raw.get('subtitle_indices') or []
        parts = [(i, subtitles[i].get('text', '')) for i in indices
                 if isinstance(i, int) and 0 <= i < len(subtitles)]
        if not parts:
            parts = [(None, raw.get('text', ''))]
        if not turns or turns[-1]['voice_id'] != voice or turns[-1]['direction'] != direction:
            turns.append({'voice_id': voice, 'direction': direction, 'text': '', 'spans': []})
        turn = turns[-1]
        for index, value in parts:
            text = re.sub(r'\s+', ' ', str(value)).strip()
            if not text:
                continue
            start = len(turn['text']) + bool(turn['text'])
            turn['text'] += (' ' if turn['text'] else '') + text
            turn['spans'].append((index, start, len(turn['text'])))
    result = []
    for turn in turns:
        text = turn['text']
        boundaries = [m.end() for m in re.finditer(r'[.!?。！？…]+["\'”’）)\]]*(?=\s|$)', text)]
        cursor = 0
        while cursor < len(text):
            candidates = [b for b in boundaries if cursor < b <= cursor + max_chars]
            if len(text) - cursor <= target_chars:
                end = len(text)
            elif candidates:
                end = next((b for b in candidates if b >= cursor + target_chars), candidates[-1])
            elif len(text) - cursor <= max_chars:
                end = len(text)
            else:
                raise ValueError('Narration sentence exceeds 1200 characters; add sentence punctuation before synthesis')
            spans = [{'index': i, 'start': max(a, cursor) - cursor, 'end': min(b, end) - cursor}
                     for i, a, b in turn['spans'] if i is not None and a < end and b > cursor]
            result.append({'id': f'seg_{len(result)+1:04d}', 'voice_id': turn['voice_id'],
                           'direction': turn['direction'], 'text': text[cursor:end],
                           'subtitle_indices': [s['index'] for s in spans], 'subtitle_spans': spans})
            cursor = end
            while cursor < len(text) and text[cursor].isspace():
                cursor += 1
    return result
