"""Local, database-free AE effect test using topic 3285's existing images."""
from __future__ import annotations

import json
import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'worker'))
import ae_highlight_worker as ae
from adobe_tools import find_aerender, find_afterfx


CASES = [
    ('01-sword-aura', 1, 'wuxia_sword_aura', ['displacement_wave', 'speedline_burst'], 0.72),
    ('02-moon-depth', 2, 'moon_fog_reveal', ['layered_depth_proxy', 'puppet_breath_idle', 'hair_cloth_wave'], 0.60),
    ('03-impact-comic', 3, 'anger_impact', ['speedline_burst', 'speech_bubble_type_on'], 0.76),
    ('04-memory-page', 4, 'memory_ink_wash', ['comic_parallax_camera', 'page_turn_transition'], 0.58),
]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--from-case', type=int, default=1)
    args = parser.parse_args()
    images = ROOT / 'output' / 'comic-test-3285' / 'images'
    output = ROOT / 'output' / 'ae-wuxia-3285'
    output.mkdir(parents=True, exist_ok=True)
    afterfx, aerender = find_afterfx(), find_aerender()
    if not afterfx or not aerender:
        raise RuntimeError('After Effects 2026 is required')
    ae.DEFAULT_WIDTH, ae.DEFAULT_HEIGHT = 960, 540
    results = []
    for name, scene_number, preset, vfx, intensity in CASES[args.from_case - 1:]:
        source = images / f'scene_{scene_number:02d}.png'
        if not source.is_file():
            raise FileNotFoundError(source)
        directory = output / name
        directory.mkdir(exist_ok=True)
        plan = {'enabled': True, 'preset': preset, 'intensity': intensity, 'vfx': vfx,
                'targets': [{'type': 'subject', 'x': .50, 'y': .53},
                            {'type': 'atmosphere', 'x': .72, 'y': .32}]}
        scene = {'ae_effect_plan': plan}
        job = ae.SceneJob('3285', '버림받은 삼류무사', {}, 0, scene,
                          scene_number, 'effect', preset, 2.5,
                          ae.GcsRef('local', source.name))
        project, movie, script = directory / 'effect.aep', directory / 'effect.mp4', directory / 'create.jsx'
        ae._write_jsx(job, source, project, movie, script)
        print(f'Creating {name}', flush=True)
        ae._run_afterfx_script(afterfx, script, project, timeout=180)
        print(f'Rendering {name}', flush=True)
        ae._run_checked([str(aerender), '-project', str(project), '-comp',
                         f'ae_highlight_{preset}', '-output', str(movie)], timeout=600)
        if not movie.is_file() or movie.stat().st_size < 1024:
            raise RuntimeError(f'Missing AE render: {movie}')
        results.append({'name': name, 'preset': preset, 'effects': vfx,
                        'movie': str(movie), 'bytes': movie.stat().st_size})
        (output / 'results.json').write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(results, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
