from services.subtitle_layout import wrap_subtitle_lines


def test_single_character_tail_is_rebalanced_without_losing_text():
    lines = wrap_subtitle_lines('ABCDEFGHIJK', len, 10)
    assert lines == ['ABCDEFGHI', 'JK']
    assert ''.join(lines) == 'ABCDEFGHIJK'


def test_japanese_punctuation_stays_attached_and_every_character_survives():
    text = '父の店を残したいと話せば、清吉はいつも耳を傾けてくれました。'
    lines = wrap_subtitle_lines(text, len, 12)
    assert ''.join(lines) == text
    assert all(len(line) <= 12 for line in lines)
    assert all(not line.startswith(('、', '。')) for line in lines[1:])
    assert all(len(line) != 1 for line in lines)


def test_existing_explicit_lines_are_preserved():
    assert wrap_subtitle_lines('first\nsecond', len, 10) == ['first', 'second']


def test_actual_ass_frame_keeps_long_japanese_inside_canvas(tmp_path):
    import subprocess
    import re
    from PIL import Image
    from services.ffmpeg_slideshow_service import _prepare_fonts_dir, _write_ass_file, _filter_path, _ffmpeg_executable

    text = '父の店を残したいと話せば、清吉はいつも耳を傾けてくれました。その顔を思うと、僕の紹介状が妙に重く感じられます。'
    settings = {'fontFamily': 'NotoSansJP-Bold', 'fontSize': 5.4, 'strokeWidth': 0}
    fonts = _prepare_fonts_dir(tmp_path, settings)
    ass = tmp_path / 'subtitles.ass'
    _write_ass_file(ass, [{'start': 0, 'end': 2, 'text': text}], settings, (640, 360), fonts)
    contents = ass.read_text(encoding='utf-8-sig')
    dialogue = next(line for line in contents.splitlines() if line.startswith('Dialogue:'))
    caption = re.sub(r'\{[^}]*\}', '', dialogue.split(',', 9)[9])
    assert caption.replace(r'\N', '') == text
    assert r'\N' in caption
    assert all(len(line) > 1 for line in caption.split(r'\N'))
    rendered = subprocess.run([_ffmpeg_executable(), '-v', 'error', '-f', 'lavfi', '-i',
        'color=black:s=640x360:d=1', '-vf',
        f"subtitles=filename='{_filter_path(str(ass))}':fontsdir='{_filter_path(fonts)}'",
        '-frames:v', '1', '-f', 'rawvideo', '-pix_fmt', 'rgb24', 'pipe:1'], capture_output=True, check=True)
    image = Image.frombytes('RGB', (640, 360), rendered.stdout).convert('L')
    bounds = image.point(lambda pixel: 255 if pixel > 20 else 0).getbbox()
    assert bounds and 0 < bounds[0] < bounds[2] < 640
    assert 0 < bounds[1] < bounds[3] < 360
