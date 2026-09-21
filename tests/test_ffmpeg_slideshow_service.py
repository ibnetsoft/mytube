import os
import shutil
from pathlib import Path

import pytest

from services.ffmpeg_slideshow_service import (
    _ass_text,
    _ffmpeg_executable,
    _is_nvenc_failure,
    _media_duration,
    _prepare_fonts_dir,
    _transition_name,
    _write_ass_file,
    render_ffmpeg_slideshow,
)


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "worker" / "fixture" / "sample_render"
REMOTE_RENDER = (ROOT / "services" / "remote_render_service.py").read_text(encoding="utf-8")


def test_remote_worker_prefers_ffmpeg_renderer_with_moviepy_compatibility_fallback():
    assert "render_ffmpeg_slideshow(" in REMOTE_RENDER
    assert "except FastRenderUnsupported" in REMOTE_RENDER
    assert "fallback=moviepy" in REMOTE_RENDER


def test_ass_settings_use_current_frontend_keys(tmp_path):
    ass_path = tmp_path / "subtitles.ass"
    _write_ass_file(
        ass_path,
        [{"start": 0, "end": 1.5, "text": "첫 줄\n둘째 줄"}],
        {
            "subtitle_font_family": "ChosunIlboMyungjo",
            "subtitle_text_color": "#12abef",
            "subtitle_stroke_width": 8,
        },
        (1280, 720),
    )

    content = ass_path.read_text(encoding="utf-8-sig")
    assert "Chosun_ilbo_myungjottf" in content
    assert "&H00EFAB12" in content
    assert r"첫 줄\N둘째 줄" in content
    assert _ass_text(r"C:\temp") == r"C:\\temp"


def test_transition_names_map_to_native_ffmpeg_effects():
    assert _transition_name("dissolve") == "dissolve"
    assert _transition_name("wipe_left") == "wipeleft"
    assert _transition_name("zoom") == "zoomin"


def test_render_font_copy_has_a_family_name_ffmpeg_can_select(tmp_path):
    fonts_dir = Path(_prepare_fonts_dir(tmp_path, {"subtitle_font_family": "GmarketSansBold"}))
    assert (fonts_dir / "GmarketSansTTFBold.ttf").is_file()
    from PIL import ImageFont

    family, style = ImageFont.truetype(str(fonts_dir / "GmarketSansTTFBold.ttf"), 20).getname()
    assert family == "GmarketSansBold"
    assert style == "Bold"

    chosun_dir = Path(_prepare_fonts_dir(tmp_path / "chosun", {"subtitle_font_family": "ChosunIlboMyungjo"}))
    chosun_font = chosun_dir / "Chosunilbo_myungjo.ttf"
    assert chosun_font.is_file()
    family, style = ImageFont.truetype(str(chosun_font), 20).getname()
    assert family == "Chosun_ilbo_myungjottf"
    assert style == "Regular"


def test_cpu_retry_is_limited_to_nvenc_failures(tmp_path):
    log_path = tmp_path / "ffmpeg.log"
    log_path.write_text("Parsed_xfade failed to configure output pad", encoding="utf-8")
    assert not _is_nvenc_failure(log_path)
    log_path.write_text("h264_nvenc: Error while opening encoder", encoding="utf-8")
    assert _is_nvenc_failure(log_path)


def test_ffmpeg_renderer_produces_exact_duration_and_progress(tmp_path):
    shutil.copytree(FIXTURE, tmp_path, dirs_exist_ok=True)
    progress = []
    output_path = render_ffmpeg_slideshow(
        temp_dir=str(tmp_path),
        images=[
            str(tmp_path / "images" / "scene1.jpg"),
            str(tmp_path / "images" / "scene2.jpg"),
        ],
        audio_path=str(tmp_path / "audio" / "voice.mp3"),
        durations=[1.0, 1.0],
        subtitles=[],
        subtitle_settings={},
        image_effects=["zoom_in", "pan_right"],
        transition_effects=["none", "dissolve"],
        resolution=(640, 360),
        use_gpu=False,
        progress_callback=lambda percent, message: progress.append((percent, message)),
    )

    assert os.path.getsize(output_path) > 0
    assert _media_duration(_ffmpeg_executable(), output_path) == pytest.approx(
        _media_duration(_ffmpeg_executable(), str(tmp_path / "audio" / "voice.mp3")),
        abs=0.1,
    )
    assert progress[0][0] == 50
    assert progress[-1][0] == 90


@pytest.mark.parametrize('effect', ['none', 'zoom_in', 'zoom_out', 'pan_left', 'pan_right', 'pan_up', 'pan_down'])
def test_scene_motion_moves_rendered_pixels_in_selected_direction(tmp_path, effect):
    import subprocess
    from PIL import Image, ImageDraw
    from services.ffmpeg_slideshow_service import _image_filter

    source = Image.new('RGB', (160, 90), 'black')
    ImageDraw.Draw(source).rectangle((60, 30, 100, 60), fill='white')
    source_path = tmp_path / 'marker.png'
    source.save(source_path)
    output = subprocess.run([
        _ffmpeg_executable(), '-v', 'error', '-loop', '1', '-i', str(source_path),
        '-filter_complex', _image_filter(0, 'motion', 160, 90, 4, 1, effect),
        '-map', '[motion]', '-frames:v', '4', '-pix_fmt', 'rgb24', '-f', 'rawvideo', 'pipe:1',
    ], capture_output=True, check=True, timeout=20).stdout
    size = 160 * 90 * 3
    boxes = [Image.frombytes('RGB', (160, 90), output[offset:offset + size]).convert('L').point(lambda value: 255 if value > 128 else 0).getbbox()
             for offset in (0, 3 * size)]
    first, last = boxes
    assert first and last
    if effect == 'none':
        assert first == last
    elif effect.startswith('zoom'):
        first_width, last_width = first[2] - first[0], last[2] - last[0]
        assert last_width > first_width if effect == 'zoom_in' else last_width < first_width
    else:
        axis = 0 if effect in ('pan_left', 'pan_right') else 1
        displacement = (last[axis] + last[axis + 2]) - (first[axis] + first[axis + 2])
        assert displacement < 0 if effect in ('pan_left', 'pan_up') else displacement > 0
