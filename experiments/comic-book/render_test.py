"""Render the first ten source scenes through the project's actual comic renderer."""
import json
import sys
import wave
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT))
from services.comic_render_service import render_comic

source = json.loads((HERE / 'source.json').read_text(encoding='utf-8'))
scenes = source['pregenerated_structure']['scenes'][:10]
durations = [5] * len(scenes)
settings = {'comic': {'version': 1, 'mode': 'comic', 'layout': 'spread',
    'turn_duration': .7, 'turn_sound': True, 'font_size': 28,
    'panels': {str(i + 1): {'fit': 'contain', 'bubble_position': 'bottom'} for i in range(10)}}}
subtitles = [{'start': i * 5, 'end': (i + 1) * 5, 'text': scene['narration']} for i, scene in enumerate(scenes)]
images = [str(HERE / 'images' / f'scene_{i+1:02}.png') for i in range(10)]
assert all(Path(p).is_file() for p in images), 'Missing scene artwork'
with wave.open(str(HERE / 'silent-timing.wav'), 'wb') as writer:
    writer.setparams((1, 2, 44100, 0, 'NONE', 'not compressed'))
    for _ in range(50): writer.writeframes(b'\0\0' * 44100)
manifest = {'topic_id': source['id'], 'title': source['generated_title'], 'scope': 'first 10 of 74 scenes',
    'test_only': True, 'narration_audio': False, 'source_modified': False,
    'settings': settings, 'durations': durations, 'subtitles': subtitles,
    'scenes': [{'scene_id': s['scene_id'], 'narration': s['narration'], 'image': f'images/scene_{i+1:02}.png'} for i,s in enumerate(scenes)]}
(HERE / 'test_manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
last = -1
def progress(percent, text):
    global last
    if percent // 10 != last:
        print(percent, text, flush=True)
        last = percent // 10
output = render_comic(temp_dir=str(HERE), images=images, durations=durations,
    audio_path=str(HERE / 'silent-timing.wav'), subtitles=subtitles, settings=settings,
    resolution=(1280,720), scene_numbers=list(range(1,11)), progress_callback=progress)
print(output, flush=True)
