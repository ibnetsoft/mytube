"""Native AE finishing-effect diagnostic, isolated from project queues and approvals.

Run on an idle AE host: python worker/ae_scene_effects_smoke.py OUTPUT_DIRECTORY
--prepare-only creates independent fixture layers/PSD and the reviewed-plan-format
input, but NEVER reports a render as successful. Pixel metrics are diagnostic,
not a substitute for watching the output or approval of production artwork.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from PIL import Image, ImageDraw
from ae_scene_animation import validate_plan
from ae_scene_effects import EFFECT_TYPES


def fixture(directory: Path):
    directory.mkdir(parents=True, exist_ok=True)
    width, height, duration = 640, 360, 3 * len(EFFECT_TYPES)
    background = Image.new('RGBA', (width, height), (34, 48, 67, 255))
    draw = ImageDraw.Draw(background)
    for x in range(0, width, 20):
        draw.line((x, 0, x, height), fill=(80, 95, 110), width=1)
    for y in range(0, height, 20):
        draw.line((0, y, width, y), fill=(80, 95, 110), width=1)
    draw.rectangle((0, 280, width, height), fill=(70, 65, 60))
    draw.text((18, 18), 'AE native effects diagnostic - independent layers', fill='white')
    character = Image.new('RGBA', (width, height))
    draw = ImageDraw.Draw(character)
    draw.ellipse((265, 80, 335, 150), fill=(222, 186, 156, 255))
    draw.rounded_rectangle((250, 150, 350, 290), radius=20, fill=(30, 130, 150, 255))
    draw.ellipse((283, 105, 288, 110), fill='black')
    draw.ellipse((312, 105, 317, 110), fill='black')
    draw.line((288, 129, 312, 129), fill=(85, 50, 40), width=2)
    prop = Image.new('RGBA', (width, height))
    draw = ImageDraw.Draw(prop)
    draw.rectangle((450, 145, 490, 210), fill=(235, 170, 45, 255), outline='white', width=2)
    draw.line((470, 210, 470, 280), fill=(170, 130, 70), width=5)
    layers = {}
    for name, image in [('background', background), ('character', character), ('lamp', prop)]:
        path = directory / (name + '.png')
        image.save(path)
        layers[name] = path
    composite = Image.alpha_composite(Image.alpha_composite(background, character), prop)
    composite.save(directory / 'source.png')
    # Preserve a genuine, independently authored PSD as inspectable sample input.
    from psd_tools import PSDImage
    from psd_tools.api.layers import PixelLayer
    psd = PSDImage.new('RGBA', (width, height))
    for name in layers:
        with Image.open(layers[name]) as image:
            PixelLayer.frompil(image, psd, name)
    psd.save(directory / 'source.psd')
    effects = []
    for index, kind in enumerate(sorted(EFFECT_TYPES)):
        entry = dict(type=kind, start=(3 * index + .25) / duration,
            end=(3 * index + 2.75) / duration, intensity=.8,
            center=[.73, .5], radius=.3, color=[1, .75, .35],
            reason='Diagnostic isolation of ' + kind + ' beside the foreground character.')
        if kind == 'heat_distortion':
            entry['target_layer'] = 'background'
        if kind in ('speedline_burst', 'subtle_vignette'):
            entry.update(center=[.5, .5], radius=.8)
        effects.append(entry)
    plan = dict(contract='ae_scene/v1', schema_version='ae_scene/v1', timing='normalized',
        width=width, height=height, output=dict(width=width, height=height),
        camera=[dict(t=t, x=.5, y=.5, scale=1.04, rotation=0) for t in (0, 1)],
        layers=[dict(id=name, role=role, z_index=index, anchor=[.5, .5], parallax=0)
            for index, (name, role) in enumerate([('background', 'background'), ('character', 'character'), ('lamp', 'prop')])],
        lights=[], effects=effects, transition=dict(in_='cut', out='cut', fraction=0),
        continuity=dict(entry='Static diagnostic', exit='Static diagnostic',
                        screen_direction='Front', light_direction='Lamp on right'))
    plan['transition']['in'] = plan['transition'].pop('in_')
    plan = validate_plan(plan)
    (directory / 'plan.json').write_text(json.dumps(plan, indent=2), encoding='utf-8')
    return dict(plan=plan, layers=layers), duration


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory', type=Path)
    parser.add_argument('--prepare-only', action='store_true')
    args = parser.parse_args()
    directory = args.directory.resolve()
    # Refuse reuse: a stale MP4/report must never be mistaken for this run.
    if directory.exists() and any(directory.iterdir()):
        raise SystemExit('Use a new empty diagnostic directory; existing evidence was preserved.')
    prepared, duration = fixture(directory)
    if args.prepare_only:
        print(json.dumps(dict(state='prepared_only_not_rendered', directory=str(directory))))
        return
    from ae_scene_production import _render_native, _video_info
    from ae_media_utils import ffmpeg, run
    native = _render_native(prepared, directory, duration)
    output = directory / 'effects-sample.mp4'
    run([ffmpeg(), '-y', '-i', str(native), '-an', '-c:v', 'libx264', '-crf', '16',
         '-pix_fmt', 'yuv420p', '-movflags', '+faststart', str(output)])
    info = _video_info(output)
    if (info['width'], info['height'], info['frames']) != (640, 360, duration * 24):
        raise RuntimeError('Unexpected diagnostic render dimensions or duration: ' + str(info))
    import numpy as np
    def frame(seconds, name):
        path = directory / (name + '.png')
        run([ffmpeg(), '-y', '-ss', str(seconds), '-i', str(output), '-frames:v', '1', str(path)])
        with Image.open(path) as image:
            return image.convert('RGB').copy()
    baseline = frame(0, 'render-baseline')
    base = np.asarray(baseline).astype(float)
    sheet = Image.new('RGB', (1280, ((len(prepared['plan']['effects']) + 1) // 2) * 390), '#101820')
    metrics = []
    for index, effect in enumerate(prepared['plan']['effects']):
        seconds = (effect['start'] + (effect['end'] - effect['start']) * .4) * duration
        image = frame(seconds, effect['type'])
        difference = np.abs(np.asarray(image).astype(float) - base)
        metrics.append(dict(type=effect['type'], seconds=seconds,
            mean_pixel_difference=float(difference.mean()),
            changed_pixel_fraction=float((difference.max(axis=2) > 5).mean())))
        x, y = index % 2 * 640, index // 2 * 390
        sheet.paste(image, (x, y + 30))
        ImageDraw.Draw(sheet).text((x + 10, y + 8), effect['type'], fill='white')
    sheet.save(directory / 'contact-sheet.png')
    report = dict(state='rendered_requires_visual_review', source_kind='independent_diagnostic_psd',
        production_approved=False, video=info, output=str(output),
        output_sha256=hashlib.sha256(output.read_bytes()).hexdigest(), effects=metrics)
    (directory / 'render-report.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps(report), flush=True)


if __name__ == '__main__':
    main()
