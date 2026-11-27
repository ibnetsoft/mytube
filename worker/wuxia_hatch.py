"""Prepare stationary blinking diagonal accents on the shared PNG patch clock.

python -m worker.wuxia_hatch --source SOURCE.png --spec SPEC.json --output DIR
Local preparation only; publish frames before attaching the manifest to a state.
"""
import argparse
import json
from pathlib import Path
from PIL import Image, ImageDraw
from worker.ambient_loop import digest, pixel_box, validate


def prepare(source, spec, directory):
    source=Path(source)
    if spec.get('source_reviewed') is not True or spec.get('source_sha256')!=digest(source):
        raise ValueError('Diagonal accent requires review of the actual source SHA')
    if not str(spec.get('reason','')).strip() or not spec.get('protected_regions'):
        raise ValueError('Diagonal accent requires a narrative reason and protected faces/text/hands')
    start=spec.get('start_ms',0);duration=spec.get('duration_ms',1400)
    interval=spec.get('blink_interval_ms',200)
    if type(duration) is not int or not 800<=duration<=2400 or type(interval) is not int or not 180<=interval<=400:
        raise ValueError('Use a readable 800-2400ms accent with 180-400ms blink intervals')
    with Image.open(source) as image:
        if image.format!='PNG' or getattr(image,'n_frames',1)!=1:raise ValueError('Expected still PNG')
        size=image.size
    dummy=dict(media_url='https://prepared.invalid/hatch.png',sha256='0'*64,gcs_bucket='pending',gcs_path='pending',duration_ms=interval)
    loop=dict(contract='ambient_loop/v1',enabled=True,source_sha256=digest(source),role='environment',width=size[0],height=size[1],
        region=spec.get('region'),protected_regions=spec['protected_regions'],start_ms=start,end_ms=start+duration,phase_ms=0,repeat=True,
        frames=[dummy,dummy],diagonal_accent=dict(contract='wuxia_diagonal_accent/v1',reason=spec['reason'],stationary_artwork=True,source_reviewed=True))
    validate(loop)
    box=pixel_box(loop['region'],size);w,h=box[2]-box[0],box[3]-box[1]
    if min(w,h)<24:raise ValueError('Accent region too small')
    direction=spec.get('direction','rising')
    if direction not in ('rising','falling'):raise ValueError('Invalid diagonal direction')
    # Restrained ink lines; only the accent blinks, never the artwork or full frame.
    tile=Image.new('RGBA',(w,h));draw=ImageDraw.Draw(tile)
    spacing=max(12,round(size[0]/90));stroke=max(1,round(size[0]/960))
    for x in range(-h,w+h,spacing):
        points=[(x,h),(x+h,0)] if direction=='rising' else [(x,0),(x+h,h)]
        draw.line(points,fill=(38,25,36,140),width=stroke)
    visible=Image.new('RGBA',size);visible.paste(tile,box[:2]);blank=Image.new('RGBA',size)
    directory=Path(directory);directory.mkdir(parents=True,exist_ok=True)
    loop['frames']=[]
    for i,patch in enumerate((visible,blank)):
        path=directory/f'hatch-{i}.png';patch.save(path)
        loop['frames'].append({**dummy,'sha256':digest(path),'local_path':str(path.resolve())})
    validate(loop)
    (directory/'manifest.local.json').write_text(json.dumps(loop,ensure_ascii=False,indent=2),encoding='utf-8')
    return loop


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('source','spec','output'):p.add_argument('--'+name,type=Path,required=True)
    a=p.parse_args();loop=prepare(a.source,json.loads(a.spec.read_text()),a.output)
    print(json.dumps(dict(prepared=True,published=False,frames=len(loop['frames']))))

if __name__=='__main__':main()
