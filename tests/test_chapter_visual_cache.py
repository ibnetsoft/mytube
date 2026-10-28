from pathlib import Path
import subprocess

import pytest
from PIL import Image

from worker.ae_media_utils import ffmpeg
from worker.chapter_visual_cache import groups, render_visual_chapters
from worker.sermon_media_worker import file_hash, video_duration


def test_visual_checkpoint_real_video_resume_and_changed_sources(tmp_path):
    images = []
    for index in range(6):
        image = tmp_path / f'{index}.png'
        Image.new('RGB', (64, 48), (index * 20, 20, 20)).save(image)
        images.append(str(image))
    calls = []
    fail = [True]
    def render(start, end, offset, duration, target):
        calls.append(start)
        if start == 2 and fail[0]:
            raise RuntimeError('simulated render interruption')
        subprocess.run([ffmpeg(), '-v', 'error', '-y', '-f', 'lavfi', '-i', 'color=c=blue:s=64x48:r=24',
            '-t', str(duration), '-c:v', 'libx264', '-pix_fmt', 'yuv420p', str(target)],
            capture_output=True, check=True, timeout=30)
    with pytest.raises(RuntimeError):
        render_visual_chapters(tmp_path, images, [.5] * 6, {'fps': 24}, render, seconds=1)
    first = tmp_path / 'visual-chapters/chapter-001.mp4'
    original = file_hash(first)
    fail[0] = False
    calls.clear()
    output = render_visual_chapters(tmp_path, images, [.5] * 6, {'fps': 24}, render, seconds=1)
    assert calls == [2, 4]
    assert file_hash(first) == original
    assert abs(video_duration(output) - 3) < .1
    calls.clear()
    render_visual_chapters(tmp_path, images, [.5] * 6, {'fps': 24}, render, seconds=1)
    assert not calls
    Image.new('RGB', (64, 48), 'red').save(images[2])
    render_visual_chapters(tmp_path, images, [.5] * 6, {'fps': 24}, render, seconds=1)
    assert calls == [2]


def test_crossfade_is_never_cut_at_a_checkpoint_boundary():
    assert list(groups([.5] * 6, seconds=1, transitions=['none', 'none', 'fade', 'none', 'none', 'none'])) == [(0, 3), (3, 5), (5, 6)]


def test_long_compositor_retains_full_audio_subtitle_and_effect_timeline(tmp_path, monkeypatch):
    from services import ffmpeg_slideshow_service as renderer
    from worker import chapter_visual_cache as cache
    original = renderer.render_ffmpeg_slideshow
    seen = []
    def checkpoint(*args, **kwargs):
        seen.append((args, kwargs))
        return str(tmp_path / 'combined.mp4')
    monkeypatch.setattr(cache, 'render_visual_chapters', checkpoint)
    calls = []
    monkeypatch.setattr(renderer, 'render_ffmpeg_slideshow', lambda **kwargs: calls.append(kwargs) or 'output.mp4')
    subs = [{'start': 3601, 'end': 3605, 'text': '日本語'}]
    cues = [{'start': 4000, 'filename': 'footsteps.wav'}]
    settings = {'bgm_path': 'music.mp3', 'bgm_start_seconds': 3000}
    output = original(temp_dir=str(tmp_path), images=['a.png', 'b.png'], durations=[2700, 2700],
        audio_path='full-narration.wav', subtitles=subs, subtitle_settings=settings,
        image_effects=['none', 'none'], transition_effects=['none', 'none'], resolution=(1920, 1080), sfx_cues=cues)
    assert output == 'output.mp4' and seen
    assert calls[0]['audio_path'] == 'full-narration.wav'
    assert calls[0]['subtitles'] is subs and calls[0]['sfx_cues'] is cues
    assert calls[0]['subtitle_settings'] is settings
    assert calls[0]['durations'] == [5400]
