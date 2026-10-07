"""Native-AE test of all four motions using synthetic media; no database writes."""
from pathlib import Path
import hashlib
import json
import sys
from PIL import Image, ImageDraw
from ae_region_motion import render
from ae_media_utils import ffmpeg, run


def main():
    import numpy as np
    directory = Path(sys.argv[1]).resolve()
    directory.mkdir(parents=True, exist_ok=True)
    source = directory / 'source.png'
    image = Image.new('RGB', (640, 360), (240, 240, 240))
    draw = ImageDraw.Draw(image)
    regions = []
    cases = [('rotate', 100, (220, 40, 40), 20),
             ('horizontal', 250, (40, 40, 220), 4),
             ('vertical', 400, (40, 180, 40), 5),
             ('scale', 550, (220, 180, 40), 10)]
    for action, x, color, amplitude in cases:
        draw.rectangle((x-25, 80, x+25, 210), fill=color)
        regions.append({'id': action, 'name': action,
                        'polygon': [[(x-30)/640, 65/360], [(x+30)/640, 65/360],
                                    [(x+30)/640, 220/360], [(x-30)/640, 220/360]],
                        'anchor': [x/640, 77/360], 'action': action,
                        'amplitude': amplitude, 'period': 2, 'cycles': 2,
                        'start': 0, 'subtitleId': 's1'})
    image.save(source)
    data = {'imageSha256': hashlib.sha256(source.read_bytes()).hexdigest(),
            'timeline': {'duration': 4, 'subtitles': [{'id': 's1', 'start': 0, 'end': 4}]},
            'regions': regions}
    output = render(source, directory, data)
    metrics = {action: [] for action, *_ in cases}
    for name, time in [('rest', 0), ('positive', .5), ('negative', 1.5), ('end', 3.958)]:
        path = directory / (name + '.png')
        run([ffmpeg(), '-y', '-ss', str(time), '-i', str(output), '-frames:v', '1', str(path)])
        pixels = np.asarray(Image.open(path).convert('RGB')).astype(float)
        for action, _, color, _ in cases:
            mask = np.max(np.abs(pixels - np.array(color)), axis=2) < 45
            ys, xs = np.nonzero(mask)
            if len(xs) < 100:
                raise RuntimeError('Rendered region is missing: ' + action)
            metrics[action].append({'x': float(xs.mean()), 'y': float(ys.mean()), 'area': len(xs)})
    checks = {
        'rotate': abs(metrics['rotate'][1]['x'] - metrics['rotate'][2]['x']) > 25,
        'horizontal': abs(metrics['horizontal'][1]['x'] - metrics['horizontal'][2]['x']) > 40,
        'vertical': abs(metrics['vertical'][1]['y'] - metrics['vertical'][2]['y']) > 25,
        'scale': metrics['scale'][1]['area'] / metrics['scale'][2]['area'] > 1.3,
    }
    report = {'passed': all(checks.values()), 'checks': checks, 'metrics': metrics, 'output': str(output)}
    (directory / 'smoke-report.json').write_text(json.dumps(report), encoding='utf-8')
    print(json.dumps(report), flush=True)
    if not report['passed']:
        raise RuntimeError('AE region motion verification failed: ' + str(checks))


if __name__ == '__main__':
    main()
