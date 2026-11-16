import math
import sys
import wave
from pathlib import Path

from PIL import Image

from services.ffmpeg_slideshow_service import render_ffmpeg_slideshow
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'worker'))
from ae_scene_production import _video_info


def test_native_master_adds_only_missing_end_frame_and_preserves_voice(tmp_path):
    picture = tmp_path / 'still.png'
    Image.new('RGB', (128, 72), (75, 40, 20)).save(picture)
    voice = tmp_path / 'voice.wav'
    with wave.open(str(voice), 'wb') as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(48000)
        audio.writeframes(bytes(2 * 96001))
    seconds = 96001 / 48000
    expected = math.ceil(seconds * 24 - 1e-7)
    output = render_ffmpeg_slideshow(
        temp_dir=str(tmp_path), images=[str(picture)], audio_path=str(voice),
        durations=[seconds], subtitles=[],
        subtitle_settings={'motion': {'enabled': True, 'fps': 24}, 'native_master_frame_count': expected},
        image_effects=['none'], transition_effects=['none'], resolution=(128, 72), use_gpu=False,
    )
    info = _video_info(output)
    assert info['frames'] == expected
    assert info['fps'] == 24
    assert abs(info['duration'] - expected / 24) < 0.002
    graph = (tmp_path / 'ffmpeg.fast.filter.txt').read_text()
    assert 'tpad=stop_mode=clone:stop=1' in graph
    assert f'trim=end_frame={expected}' in graph
