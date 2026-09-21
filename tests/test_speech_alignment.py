import ast
import re
from pathlib import Path

from services.speech_alignment import aligned_span, validate_alignment
import pytest


def test_subtitles_follow_uneven_speech_and_internal_pause():
    tree = ast.parse(Path('services/remote_render_service.py').read_text(encoding='utf-8-sig'))
    body = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in ('_retime_subtitles_from_worker_tts', '_subtitle_weight')]
    scope = {'re': re}
    exec(compile(ast.Module(body=body, type_ignores=[]), '<retime>', 'exec'), scope)
    text = '가나 다라'
    alignment = {'characters': list(text), 'character_start_times_seconds': [.2, .4, .6, 2.1, 2.4], 'character_end_times_seconds': [.4, .6, 2.1, 2.4, 2.7]}
    segments = [{'id': 's', 'text': text, 'subtitle_indices': [0, 1], 'subtitle_spans': [{'index': 0, 'start': 0, 'end': 2}, {'index': 1, 'start': 3, 'end': 5}]}]
    result = scope['_retime_subtitles_from_worker_tts']([{'text': '가나'}, {'text': '다라'}], segments, [{'id': 's', 'start': 10, 'end': 13, 'alignment': alignment}])
    assert [(s['start'], s['end']) for s in result] == [(10.2, 10.6), (12.1, 12.7)]


def test_wrong_transcript_is_not_silently_timed():
    with pytest.raises(ValueError, match='transcript'):
        validate_alignment('다른 문장', {'characters': ['가'], 'character_start_times_seconds': [0], 'character_end_times_seconds': [1]})


def test_explicit_postprocessing_speed_transforms_timestamps_once():
    alignment = {'characters': ['가'], 'character_start_times_seconds': [.4], 'character_end_times_seconds': [1.4]}
    assert aligned_span('가', alignment, 0, 1, offset=3, speed_ratio=2) == (3.2, 3.7)
