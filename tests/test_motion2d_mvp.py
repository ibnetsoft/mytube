import json
import math
import struct
import subprocess
import sys
import wave
from pathlib import Path

import imageio_ffmpeg
import pytest
from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'worker'))
from motion2d_mvp import render


def fixture(tmp_path):
    size = (64, 64)
    Image.new('RGB', size, 'white').save(tmp_path / 'source.png')
    for name, box, color in [('closed', (20, 40, 44, 41), 'black'), ('open', (20, 37, 44, 44), 'black'), ('blink', (18, 20, 46, 22), 'black'), ('hair', (10, 0, 54, 12), 'blue')]:
        layer = Image.new('RGBA', size)
        ImageDraw.Draw(layer).rectangle(box, fill=color)
        layer.save(tmp_path / (name + '.png'))
    with wave.open(str(tmp_path / 'voice.wav'), 'wb') as out:
        out.setparams((1, 2, 48000, 0, 'NONE', 'not compressed'))
        out.writeframes(b''.join(struct.pack('<h', int(5000 * math.sin(2 * math.pi * 440 * n / 48000))) for n in range(48000 * 4)))
    data = {'source': 'source.png', 'audio': 'voice.wav', 'mouths': {'closed': 'closed.png', 'open': 'open.png'}, 'mouth_cues': [{'start': 1, 'end': 2, 'pose': 'open'}], 'blink': {'sprite': 'blink.png', 'start': 2, 'end': 2.2}, 'hair': {'sprite': 'hair.png', 'anchor_y': 0, 'amplitude_px': 4, 'period': 2}}
    manifest = tmp_path / 'manifest.json'
    manifest.write_text(json.dumps(data), encoding='utf-8')
    return manifest, data


def test_render_96_frames_with_audio_and_visible_cues(tmp_path):
    manifest, _ = fixture(tmp_path)
    output = tmp_path / 'result.mp4'
    result = render(manifest, output)
    assert result['frames'] == 96
    assert imageio_ffmpeg.count_frames_and_secs(str(output)) == (96, 4.0)
    reader = imageio_ffmpeg.read_frames(str(output), pix_fmt='rgb24')
    info = next(reader)
    frames = list(reader)
    assert info['size'] == (64, 64)
    assert len(frames) == 96
    decoded = subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), '-v', 'error', '-i', str(output), '-map', '0:a:0', '-ac', '1', '-ar', '48000', '-f', 's16le', 'pipe:1'], capture_output=True, check=True).stdout
    assert abs(len(decoded) / 2 / 48000 - 4) < .06
    def pixel(frame, x, y):
        i = (y * 64 + x) * 3
        return sum(frame[i:i+3])
    assert pixel(frames[30], 30, 38) < pixel(frames[0], 30, 38) - 100
    assert pixel(frames[49], 30, 21) < pixel(frames[0], 30, 21) - 100
    with pytest.raises(ValueError, match='already exists'):
        render(manifest, output)


def test_invalid_cues_do_not_publish_output(tmp_path):
    manifest, data = fixture(tmp_path)
    data['mouth_cues'] = [{'start': 1, 'end': 2, 'pose': 'missing'}]
    manifest.write_text(json.dumps(data), encoding='utf-8')
    output = tmp_path / 'result.mp4'
    with pytest.raises(ValueError, match='Mouth cues'):
        render(manifest, output)
    assert not output.exists()
