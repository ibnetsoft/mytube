from pathlib import Path

import numpy as np
from PIL import Image

from services.motion_render_service import MotionFrames


def _scene(transition, **extra):
    return {
        'source': 'image', 'fit': 'contain', 'direction': 'Test boundary',
        'keys': [dict(t=t, x=.5, y=.5, scale=1, rotation=0, opacity=100) for t in (0, 1)],
        'effects': [], 'transition': transition, **extra,
    }


def test_crossfade_blends_the_previous_shot_into_the_next_without_black_or_retiming(tmp_path):
    first, second = tmp_path / 'first.png', tmp_path / 'second.png'
    Image.new('RGB', (64, 36), '#ff0000').save(first)
    Image.new('RGB', (64, 36), '#0000ff').save(second)
    motion = {
        'version': 1, 'enabled': True, 'aspect': '16:9', 'fps': 24,
        'scenes': {'1': _scene('cut'), '2': _scene('crossfade', transition_seconds=.24)},
    }
    frames = MotionFrames([str(first), str(second)], [1, 1], [], {'motion': motion}, (64, 36), '')
    try:
        frames.frame(.96)
        at_boundary = frames.frame(1.0)[18, 32]
        halfway = frames.frame(1.12)[18, 32]
        after = frames.frame(1.24)[18, 32]
    finally:
        frames.close()
    assert tuple(at_boundary) == (255, 0, 0)
    assert 110 <= int(halfway[0]) <= 145 and 110 <= int(halfway[2]) <= 145
    assert tuple(after) == (0, 0, 255)


def test_final_mux_pads_short_encoded_tail_without_retiming_late_scene_cuts(tmp_path):
    import wave
    from moviepy import VideoFileClip
    from services.motion_render_service import render_motion

    paths=[]
    for name,color in [('red','#ff0000'),('green','#00ff00'),('blue','#0000ff')]:
        path=tmp_path/f'{name}.png';Image.new('RGB',(64,36),color).save(path);paths.append(str(path))
    durations=[1.03,1.07,1.09]
    audio=tmp_path/'voice.wav'
    with wave.open(str(audio),'wb') as wav:
        wav.setnchannels(1);wav.setsampwidth(2);wav.setframerate(8000)
        wav.writeframes(np.zeros(round(sum(durations)*8000),dtype='<i2').tobytes())
    motion={'version':1,'enabled':True,'aspect':'16:9','fps':24,
        'scenes':{str(i):_scene('cut') for i in (1,2,3)}}
    final_dir=tmp_path/'final';final_dir.mkdir()
    output=render_motion(temp_dir=str(final_dir),images=paths,durations=durations,audio_path=str(audio),
        subtitles=[],settings={'motion':motion},resolution=(64,36),scene_numbers=[1,2,3])
    with VideoFileClip(output,audio=False) as clip:
        # Hard cuts are quantized to the first 24fps frame at or after each
        # scheduled boundary; the final mux must not stretch the whole visual.
        assert int(np.argmax(clip.get_frame(1.0)[18,32])) == 0
        assert int(np.argmax(clip.get_frame(25/24)[18,32])) == 1
        assert int(np.argmax(clip.get_frame(50/24)[18,32])) == 1
        assert int(np.argmax(clip.get_frame(51/24)[18,32])) == 2
