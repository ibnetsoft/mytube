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
    assert "Chosunilbo_myungjo" in content
    assert "&H00EFAB12" in content
    assert r"첫 줄\N둘째 줄" in content
    assert _ass_text(r"C:\temp") == r"C:\\temp"


def test_transition_names_map_to_native_ffmpeg_effects():
    assert _transition_name("dissolve") == "dissolve"
    assert _transition_name("wipe_left") == "wipeleft"
    assert _transition_name("zoom") == "zoomin"


@pytest.mark.parametrize("effect", ["zoom_in", "zoom_out", "pan_left", "pan_right"])
@pytest.mark.parametrize("speed", [0.5, 1.5, 3])
def test_motion_speed_renders_full_duration(effect, speed):
    import subprocess
    from services.ffmpeg_slideshow_service import _image_filter

    graph = _image_filter(0, "motion", 320, 180, 24, 0.5, effect, speed)
    result = subprocess.run([
        _ffmpeg_executable(), "-v", "error", "-f", "lavfi", "-i",
        "testsrc2=size=320x180:rate=24", "-filter_complex", graph,
        "-map", "[motion]", "-f", "rawvideo", "-pix_fmt", "rgb24", "pipe:1",
    ], capture_output=True, check=True)
    frame_size = 320 * 180 * 3
    assert len(result.stdout) == 12 * frame_size
    assert result.stdout[:frame_size] != result.stdout[-frame_size:]


def test_motion_defaults_and_limits():
    from services.ffmpeg_slideshow_service import _image_filter
    assert "0.060000" in _image_filter(0, "v", 320, 180, 24, 1, "zoom_in")
    assert "z='1.120000'" in _image_filter(0, "v", 320, 180, 24, 1, "pan_left")
    assert "0.120000" in _image_filter(0, "v", 320, 180, 24, 1, "zoom_in", 99)
    assert "0.060000" in _image_filter(0, "v", 320, 180, 24, 1, "zoom_in", "invalid")


@pytest.mark.parametrize("width", [640, 1280, 1920])
@pytest.mark.parametrize("stroke", [0, 15, 50])
def test_rendered_outline_matches_preview_outer_radius(tmp_path, width, stroke):
    import subprocess
    from PIL import Image
    from services.ffmpeg_slideshow_service import _filter_path

    height = width * 9 // 16
    ass = tmp_path / "outline.ass"
    settings = {"fontFamily": "GmarketSansBold", "fontSize": 10,
                "subtitle_text_color": "#ffffff", "subtitle_stroke_color": "#ffffff",
                "subtitle_stroke_width": stroke}
    fonts = _prepare_fonts_dir(tmp_path, settings)

    def bounds(value):
        settings["subtitle_stroke_width"] = value
        _write_ass_file(ass, [{"start": 0, "end": 1, "text": "I"}],
                        settings, (width, height), fonts)
        result = subprocess.run([
            _ffmpeg_executable(), "-v", "error", "-f", "lavfi", "-i",
            f"color=black:s={width}x{height}", "-vf",
            f"subtitles=filename='{_filter_path(str(ass))}':fontsdir='{_filter_path(fonts)}'",
            "-frames:v", "1", "-f", "rawvideo", "-pix_fmt", "rgb24", "pipe:1",
        ], capture_output=True, check=True)
        mask = Image.frombytes("RGB", (width, height), result.stdout).convert("L")
        return mask.point(lambda pixel: 255 if pixel > 127 else 0).getbbox()

    plain, outlined = bounds(0), bounds(stroke)
    # CSS stroke is centered on the edge; paintOrder='stroke fill' hides half.
    expected_radius = stroke * width / 1920 / 2
    assert plain[0] - outlined[0] == pytest.approx(expected_radius, abs=1.2)
    assert outlined[2] - plain[2] == pytest.approx(expected_radius, abs=1.2)


@pytest.mark.parametrize("opacity", [0, 0.5, 1])
def test_rounded_background_is_rendered_by_libass(tmp_path, opacity):
    import subprocess
    from PIL import Image
    from services.ffmpeg_slideshow_service import _filter_path

    ass = tmp_path / "rounded.ass"
    settings = {
        "fontFamily": "GmarketSansBold", "fontSize": 10,
        "bgEnabled": True, "bgColor": "#ff0000", "bgOpacity": opacity,
        "strokeWidth": 0,
    }
    fonts = _prepare_fonts_dir(tmp_path, settings)
    _write_ass_file(ass, [{"start": 0, "end": 1, "text": "TEST\nBAR"}], settings, (640, 360), fonts)
    content = ass.read_text(encoding="utf-8-sig")
    assert content.count("Dialogue: 0,") == 1
    assert content.count("Dialogue: 1,") == 2
    result = subprocess.run([
        _ffmpeg_executable(), "-v", "error", "-f", "lavfi", "-i", "color=black:s=640x360",
        "-vf", f"subtitles=filename='{_filter_path(str(ass))}':fontsdir='{_filter_path(fonts)}'",
        "-frames:v", "1", "-f", "rawvideo", "-pix_fmt", "rgb24", "pipe:1",
    ], capture_output=True, check=True)
    image = Image.frombytes("RGB", (640, 360), result.stdout)
    image.save(tmp_path / "rounded.png")
    # Find only the red background, excluding white glyphs.
    pixels = image.load()
    red = [(x, y) for y in range(360) for x in range(640)
           if pixels[x, y][0] > pixels[x, y][1] + 30]
    if opacity == 0:
        assert not red
        return
    left, right = min(x for x, y in red), max(x for x, y in red)
    top, bottom = min(y for x, y in red), max(y for x, y in red)
    assert pixels[left+1, top+1][0] < 20
    assert pixels[right-1, bottom-1][0] < 20
    assert pixels[320, top+3][0] == pytest.approx(255 * opacity, abs=10)


def test_render_font_copy_has_a_family_name_ffmpeg_can_select(tmp_path):
    fonts_dir = Path(_prepare_fonts_dir(tmp_path, {"subtitle_font_family": "GmarketSansBold"}))
    assert (fonts_dir / "GmarketSansBold.ttf").is_file()
    from PIL import ImageFont

    family, style = ImageFont.truetype(str(fonts_dir / "GmarketSansBold.ttf"), 20).getname()
    assert family == "GmarketSansBold"
    assert style == "Bold"

    chosun_dir = Path(_prepare_fonts_dir(tmp_path / "chosun", {"subtitle_font_family": "ChosunIlboMyungjo"}))
    chosun_font = chosun_dir / "Chosunilbo_myungjo.ttf"
    assert chosun_font.is_file()
    family, style = ImageFont.truetype(str(chosun_font), 20).getname()
    assert family == "Chosunilbo_myungjo"
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


@pytest.mark.parametrize('effect', ['zoom_in', 'zoom_out'])
def test_zoom_does_not_wobble_off_centre(tmp_path, effect):
    import subprocess
    import numpy as np
    from PIL import Image, ImageDraw
    from services.ffmpeg_slideshow_service import _image_filter
    source = Image.new('RGB', (320, 180), 'black')
    ImageDraw.Draw(source).rectangle((120, 65, 199, 114), fill='white')
    path = tmp_path / 'centre.png'
    source.save(path)
    output = subprocess.run([
        _ffmpeg_executable(), '-v', 'error', '-loop', '1', '-i', str(path),
        '-filter_complex', _image_filter(0, 'motion', 320, 180, 30, 2, effect),
        '-map', '[motion]', '-frames:v', '60', '-pix_fmt', 'gray', '-f', 'rawvideo', 'pipe:1',
    ], capture_output=True, check=True, timeout=30).stdout
    frames = np.frombuffer(output, dtype=np.uint8).reshape(-1, 180, 320).astype(float)
    mass = frames.sum(axis=(1, 2))
    centres_x = (frames.sum(axis=1) * np.arange(320)).sum(axis=1) / mass
    centres_y = (frames.sum(axis=2) * np.arange(180)).sum(axis=1) / mass
    assert np.ptp(centres_x) < .15
    assert np.ptp(centres_y) < .15
