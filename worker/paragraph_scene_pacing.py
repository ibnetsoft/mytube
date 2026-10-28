"""Paragraph-first story scenes, retaining the opening only once per story."""
import math
import re

from services.scene_pacing import pacing_schedule

MODE = 'paragraph_min18_v1'
MIN_SECONDS = 18
MAX_SECONDS = 180
OPENING_SECONDS = 597


def opening_schedule(seconds, elapsed=0):
    """Chapter boundaries do not restart the opening's 60 short scenes."""
    if elapsed >= OPENING_SECONDS:
        return []
    if elapsed:
        raise ValueError('A chapter must not split the fixed opening.')
    return pacing_schedule(min(seconds, OPENING_SECONDS))


def paragraph_scenes(paragraphs, seconds, chars_per_second):
    """Prefer paragraph boundaries; split oversized paragraphs at sentences."""
    if seconds < MIN_SECONDS or chars_per_second <= 0:
        raise ValueError('Paragraph scenes require at least 18 seconds.')
    if not isinstance(paragraphs, list) or not paragraphs:
        raise ValueError('Natural narration paragraphs are required.')
    texts = []
    for value in paragraphs:
        if not isinstance(value, str) or not value.strip():
            raise ValueError('Every narration paragraph must contain text.')
        texts.extend(p.strip() for p in re.split(r'\n\s*\n', value.strip()) if p.strip())
    weights = [len(re.sub(r'\s', '', text)) for text in texts]
    total = sum(weights)
    if total < math.ceil(MIN_SECONDS * chars_per_second):
        raise ValueError('Narration is too short for an 18-second scene.')
    # Enforce both the spoken estimate and the allocated chapter runtime.
    lower = max(MIN_SECONDS * chars_per_second, MIN_SECONDS * total / seconds)
    upper = min(MAX_SECONDS * chars_per_second, MAX_SECONDS * total / seconds)
    source = '\n\n'.join(texts)
    paragraph_ends, boundaries, offset = set(), {0}, 0
    for text in texts:
        for match in re.finditer(r'''[。！？!?]+[」』”’"'）)\]]*|\.(?=\s|$|[」』”’"'）)\]])[」』”’"'）)\]]*''', text):
            boundaries.add(offset + match.end())
        offset += len(text)
        paragraph_ends.add(offset)
        boundaries.add(offset)
        offset += 2
    positions = sorted(boundaries)
    prefix = [0]
    for char in source:
        prefix.append(prefix[-1] + (not char.isspace()))
    # Minimize cuts inside paragraphs, then unnecessary paragraph merges.
    # This also rebalances a short tail instead of appending it past 180s.
    best = {0: ((0, 0, 0), None)}
    para_prefix = [0]
    for position in positions:
        para_prefix.append(para_prefix[-1] + (position in paragraph_ends))
    for end in range(1, len(positions)):
        for start in range(end - 1, -1, -1):
            weight = prefix[positions[end]] - prefix[positions[start]]
            if weight > upper + 1e-8:
                break
            if weight + 1e-8 < lower or start not in best:
                continue
            cost = best[start][0]
            merged = para_prefix[end] - para_prefix[start + 1]
            candidate = (cost[0] + (positions[end] not in paragraph_ends), cost[1] + merged, cost[2] + 1)
            if end not in best or candidate < best[end][0]:
                best[end] = (candidate, start)
    if len(positions) - 1 not in best:
        raise ValueError('Cannot fit narration into 18–180 second scenes at sentence boundaries; rewrite overlong sentences or rebalance paragraphs.')
    groups, end = [], len(positions) - 1
    while end:
        start = best[end][1]
        left, right = positions[start], positions[end]
        groups.append({'text': source[left:right].strip(), 'weight': prefix[right] - prefix[left]})
        end = start
    groups.reverse()
    durations = [math.floor(seconds * group['weight'] / total) for group in groups]
    remainder = seconds - sum(durations)
    order = sorted(range(len(groups)), key=lambda i: seconds * groups[i]['weight'] / total - durations[i], reverse=True)
    for i in order[:remainder]:
        durations[i] += 1
    for group, duration in zip(groups, durations):
        if not MIN_SECONDS <= duration <= MAX_SECONDS:
            raise ValueError('A paragraph scene must last 18–180 seconds.')
        group['duration_seconds'] = duration
        del group['weight']
    return groups
