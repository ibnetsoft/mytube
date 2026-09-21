from services.narration_segments import sentence_segments
from services.subtitle_layout import subtitle_font_pixels


def test_old_byte_limit_does_not_split_a_sentence_or_change_voice():
    subtitles = [{'text': t} for t in ['그 일을 달갑지 않게 여긴 사람이', '있었습니다. 시아버지와 곡식을',
                                       '사고팔던 백 주인이었습니다. 그는', '돈을 빌렸습니다.', '누구세요?']]
    raw = [{'voice_id': 'narrator', 'subtitle_indices': [0]},
           {'voice_id': 'narrator', 'subtitle_indices': [1, 2, 3]},
           {'voice_id': 'actor', 'subtitle_indices': [4]}]
    segments = sentence_segments(raw, subtitles, target_chars=18)
    assert segments[0]['text'] == '그 일을 달갑지 않게 여긴 사람이 있었습니다.'
    assert segments[1]['text'] == '시아버지와 곡식을 사고팔던 백 주인이었습니다.'
    assert segments[2]['text'] == '그는 돈을 빌렸습니다.'
    assert segments[3]['voice_id'] == 'actor'
    assert segments[0]['subtitle_indices'] == [0, 1]
    assert segments[1]['subtitle_indices'] == [1, 2]


def test_size_matches_preview_at_every_output_resolution():
    for width in (440, 1280, 1920, 3840):
        assert abs(subtitle_font_pixels(6.5, width) / width - 18.2 / 440) < 1e-9


def test_screenshot_subtitle_stays_one_line(tmp_path):
    from services.ffmpeg_slideshow_service import _write_ass_file
    path = tmp_path / 'sample.ass'
    text = '사고팔던 백 주인이었습니다. 그는'
    _write_ass_file(path, [{'text': text, 'start': 0, 'end': 2}],
                    {'subtitle_font_family': 'ChosunIlboMyungjo', 'subtitle_font_size': 6.5,
                     'subtitle_bg_enabled': True}, (1920, 1080))
    ass = path.read_text(encoding='utf-8-sig')
    assert '79.418' in ass
    assert 'WrapStyle: 2' in ass
    assert ass.count('Dialogue: 1,') == 1
    assert text in ass


def test_subtitle_spanning_two_sentences_keeps_both_audio_ranges():
    import ast
    import re
    from pathlib import Path
    source = Path('services/remote_render_service.py').read_text(encoding='utf-8-sig')
    tree = ast.parse(source)
    body = [n for n in tree.body if isinstance(n, ast.FunctionDef)
            and n.name in ('_retime_subtitles_from_worker_tts', '_subtitle_weight')]
    scope = {'re': re}
    exec(compile(ast.Module(body=body, type_ignores=[]), '<retime>', 'exec'), scope)
    subs = [{'text': '첫 문장입니다. 둘째'}, {'text': '문장입니다.'}]
    segments = sentence_segments([{'voice_id': 'n', 'subtitle_indices': [0, 1]}], subs, target_chars=3)
    timeline = [{'id': segments[0]['id'], 'start': 0, 'end': 2},
                {'id': segments[1]['id'], 'start': 2.26, 'end': 5}]
    result = scope['_retime_subtitles_from_worker_tts'](subs, segments, timeline)
    assert result[0]['start'] == 0
    assert 2.26 < result[0]['end'] < result[1]['start'] < 5
    assert result[1]['end'] == 5
