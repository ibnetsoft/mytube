from pathlib import Path
import json
import subprocess
import pytest


ROOT = Path(__file__).resolve().parents[1]
GLOBAL_CSS = (ROOT / "auth-web" / "app" / "globals.css").read_text(encoding="utf-8")
FONT_DIR = ROOT / "auth-web" / "public" / "fonts"


def test_subtitle_fonts_are_served_locally_without_a_noonnu_cdn_request():
    assert "jsdelivr.net/gh/projectnoonnu" not in GLOBAL_CSS
    assert "font-family: 'Gungsuh'" not in GLOBAL_CSS

    expected_files = set(json.loads((FONT_DIR / 'catalog.json').read_text()).values())
    assert len(expected_files) == 15
    assert expected_files <= {path.name for path in FONT_DIR.iterdir() if path.is_file()}
    assert 'fonts.googleapis.com' not in GLOBAL_CSS
    for file_name in expected_files:
        assert f"/fonts/{file_name}" in GLOBAL_CSS


@pytest.mark.parametrize('family', list(json.loads((FONT_DIR / 'catalog.json').read_text())))
def test_every_web_font_is_selected_by_libass_without_korean_fallback(tmp_path, family):
    from PIL import ImageFont
    from services.ffmpeg_slideshow_service import (
        _prepare_fonts_dir, _write_ass_file, _filter_path, _ffmpeg_executable, _ass_font_family,
    )
    settings = {'fontFamily': family, 'fontSize': 5, 'bgEnabled': True, 'strokeWidth': 0}
    fonts = _prepare_fonts_dir(tmp_path, settings)
    font_file = next(Path(fonts).glob('*.ttf'))
    assert ImageFont.truetype(str(font_file), 32).getname()[0] == _ass_font_family(family)
    ass = tmp_path / 'font.ass'
    _write_ass_file(ass, [{'start': 0, 'end': 1, 'text': '가나다라마바사 아침 햇살 ABC 123'}], settings, (1280, 720), fonts)
    result = subprocess.run([
        _ffmpeg_executable(), '-hide_banner', '-f', 'lavfi', '-i', 'color=c=0x456789:s=1280x720',
        '-vf', f"subtitles=filename='{_filter_path(str(ass))}':fontsdir='{_filter_path(fonts)}'",
        '-frames:v', '1', '-y', str(tmp_path / 'font.png'),
    ], capture_output=True, check=True, timeout=30)
    log = result.stderr.decode('utf-8', 'replace')
    selections = [line for line in log.splitlines() if 'fontselect:' in line]
    assert len(selections) == 1, log
    assert f'({_ass_font_family(family)},' in selections[0]
    assert 'failed to find any fallback' not in log.lower()
