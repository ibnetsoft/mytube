"""Exercise the separately built FilmCraft renderer with generated image/audio fixtures."""
from __future__ import annotations

import json
import math
import struct
import subprocess
import sys
import tempfile
import wave
from pathlib import Path

from PIL import Image, ImageDraw

from filmcraft import ROOT, binary, sha


def main():
    cli, manifest = binary()
    directory = Path(tempfile.mkdtemp(prefix='verification-', dir=cli.parent))
    project = directory / 'sample.fcproj'
    still = directory / 'source.png'
    voice = directory / 'tone.wav'
    output = directory / 'sample.mp4'
    image = Image.new('RGB', (320, 180), (220, 30, 40))
    ImageDraw.Draw(image).rectangle((160, 0, 319, 179), fill=(30, 60, 220))
    image.save(still)
    with wave.open(str(voice), 'wb') as audio:
        audio.setparams((1, 2, 48000, 0, 'NONE', 'not compressed'))
        audio.writeframes(b''.join(struct.pack('<h', round(6000 * math.sin(2 * math.pi * 440 * i / 48000)))
                                   for i in range(96000)))

    def execute(command, params, new=False):
        args = [str(cli), '--compact']
        args += ['--save-as', str(project)] if new else ['--project', str(project), '--save']
        result = subprocess.run(args + ['exec', command, json.dumps(params)],
                                check=True, capture_output=True, text=True, encoding='utf-8')
        return json.loads(result.stdout)

    execute('file.newSequence', {'name': 'AIR optional renderer verification', 'width': 320,
                                'height': 180, 'fps': 24}, new=True)
    items = execute('file.import', {'paths': [str(still), str(voice)]})['items']
    duration = 2 * 254016000000
    execute('timeline.place', {'item': items[0], 'track': 'V1', 'time': 0,
                               'duration': duration, 'audio': False})
    execute('timeline.place', {'item': items[1], 'track': 'A1', 'time': 0,
                               'duration': duration, 'video': False})
    original_project_hash = sha(project)
    command = [sys.executable, str(ROOT / 'scripts/filmcraft.py'), 'render', str(project)]
    subprocess.run(command + [str(output), '--gpu-rendering', 'off'], check=True)
    import numpy as np
    from moviepy import VideoFileClip
    with VideoFileClip(str(output)) as clip:
        assert tuple(clip.size) == (320, 180), clip.size
        assert abs(clip.duration - 2) < 1 / 24, clip.duration
        assert clip.audio is not None, 'Missing encoded audio'
        decoded = list(clip.iter_frames(dtype='uint8'))
        assert len(decoded) == 48, len(decoded)
        for frame in decoded:
            assert np.abs(frame[30:150, 30:130].mean(axis=(0, 1)) - [220, 30, 40]).max() < 15
            assert np.abs(frame[30:150, 190:290].mean(axis=(0, 1)) - [30, 60, 220]).max() < 15
        audio = clip.audio.to_soundarray(fps=48000)
        rms = float(np.sqrt(np.mean(audio ** 2)))
        assert .03 < rms < .25, rms
        mono = audio.mean(axis=1)
        frequency = float(np.fft.rfftfreq(len(mono), 1 / 48000)[np.abs(np.fft.rfft(mono)).argmax()])
        assert abs(frequency - 440) < 2, frequency
    output_hash = sha(output)
    duplicate = subprocess.run(command + [str(output)], capture_output=True)
    assert duplicate.returncode != 0 and sha(output) == output_hash, 'Existing render was overwritten'
    missing = directory / 'source-hidden.png'
    still.rename(missing)
    try:
        offline = subprocess.run(command + [str(directory / 'offline.mp4'), '--gpu-rendering', 'off'],
                                 capture_output=True)
        assert offline.returncode != 0, 'Missing source was silently accepted'
    finally:
        missing.rename(still)
    assert sha(project) == original_project_hash, 'Rendering changed the native project'
    result = {'engine': 'filmcraft', 'revision': manifest['revision'], 'passed': True,
              'video': {'width': 320, 'height': 180, 'fps': 24, 'decoded_frames': 48, 'duration': 2},
              'audio': {'rms': rms, 'dominant_frequency_hz': frequency},
              'checks': ['decoded_colors_all_frames', 'encoded_audio', 'source_unchanged',
                         'existing_output_preserved', 'offline_media_rejected'],
              'output': str(output), 'output_sha256': output_hash}
    (directory / 'verification.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(json.dumps(result, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    main()
