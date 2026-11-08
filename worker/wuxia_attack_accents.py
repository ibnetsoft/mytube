"""Attach selected action accents to a NEW package copy after actual-source review.

No random/all-scenes application and no changes to original artwork or final episodes.
The web editor owns vector sampling; native AE consumes those frozen samples.
"""
import argparse
import copy
import hashlib
import json
import math
from pathlib import Path

CONTRACT = 'wuxia_attack_accent/v1'
TYPES = {'electric_discharge': .6, 'attack_speedline': .35, 'contact_flash': .125}


def attach(package, selections, source_root):
    result = copy.deepcopy(package)
    scenes = result['scenes']
    root = Path(source_root).resolve()
    seen = set()
    for selection in selections:
        scene = next(s for s in scenes if s['scene_id'] == selection['scene_id'])
        state = next(s for s in scene['states'] if s['asset_id'] == selection['asset_id'])
        key = (scene['scene_id'], state['asset_id'])
        if key in seen:
            raise ValueError('Duplicate state accent selection')
        seen.add(key)
        path = (root / selection['source_file']).resolve()
        if not path.is_relative_to(root) or hashlib.sha256(path.read_bytes()).hexdigest() != state['sha256']:
            raise ValueError('Review source file must match the stored artwork SHA')
        from PIL import Image
        with Image.open(path) as image:
            if image.format != 'PNG' or getattr(image, 'n_frames', 1) != 1 or image.width * image.height > 16_000_000:
                raise ValueError('Attack source must be the actual still PNG')
        if not isinstance(state.get('face_exclusion_boxes'),list):
            raise ValueError('Actual-source head review is required')
        review = selection['review']
        if (review.get('contract') != CONTRACT or review.get('source_sha256') != state['sha256']
                or review.get('source_reviewed') is not True
                or any(not isinstance(review.get(k), str) or not review[k].strip()
                       for k in ('event', 'materials', 'reason', 'motion_evidence'))):
            raise ValueError('Actual artwork, depicted attack and material review are required')
        boxes = review.get('protected_boxes')
        def number(v): return type(v) in (int, float) and math.isfinite(v)
        def point(p): return isinstance(p, list) and len(p) == 2 and all(number(v) and 0 <= v <= 1 for v in p)
        if (not isinstance(boxes, list) or len(boxes) > 16 or any(not isinstance(b, list) or len(b) != 4
                or not all(number(v) and 0 <= v <= 1 for v in b) or b[0] >= b[2] or b[1] >= b[3] for b in boxes)):
            raise ValueError('Review all faces, hands, weapons and baked lettering, including empty regions')
        effects = selection.get('effects')
        if not isinstance(effects, list) or len(effects) > 3 or len({e.get('type') for e in effects}) != len(effects):
            raise ValueError('Select each motivated accent at most once; an empty selection is valid')
        if effects and state.get('energy_only_motion'):
            raise ValueError('Preserve energy-only source motion; do not add attack accents')
        scene['effects']=[e for e in scene.get('effects',[]) if not(e.get('automation')==CONTRACT and e.get('asset_id')==state['asset_id'])]
        for effect in effects:
            kind = effect.get('type')
            if kind not in TYPES or not number(effect.get('duration_seconds')) or not 0 < effect['duration_seconds'] <= TYPES[kind]:
                raise ValueError('Unsupported accent or duration')
            if not number(effect.get('intensity')) or not 0 < effect['intensity'] <= 1 or not number(effect.get('radius')) or not 0 < effect['radius'] <= 1:
                raise ValueError('Invalid accent strength or radius')
            trajectory = effect.get('attack_path')
            if (not isinstance(trajectory, list) or not 2 <= len(trajectory) <= 4 or not all(point(p) for p in trajectory)
                    or not point(effect.get('center')) or math.dist(trajectory[-1], effect['center']) > .02
                    or math.hypot((trajectory[0][0]-trajectory[-1][0])*1920,(trajectory[0][1]-trajectory[-1][1])*1080) < 8
                    or any(math.hypot((b[0]-a[0])*1920,(b[1]-a[1])*1080)<8 for a,b in zip(trajectory,trajectory[1:]))):
                raise ValueError('Review weapon/fist travel and its actual contact endpoint')
            if review.get('timing_basis') == 'voice_anchor':
                if not effect.get('voice_binding', {}).get('exact_anchor') or not effect.get('quote') or effect.get('contact_at_seconds') is not None:
                    raise ValueError('Exact saved voice anchor required')
            elif review.get('timing_basis') != 'scene_local' or not number(effect.get('contact_at_seconds')) or effect['contact_at_seconds'] < 0 or effect.get('voice_binding'):
                raise ValueError('Explicit local contact time required for silent action')
            delay = effect.get('delay_seconds', 0)
            if not number(delay) or not 0 <= delay <= .3 or kind == 'attack_speedline' and delay:
                raise ValueError('Speedlines lead contact; flash/discharge cannot precede it')
            if kind == 'electric_discharge' and review.get('electricity_motivated') is not True:
                raise ValueError('Do not invent electricity for an ordinary attack')
            if kind == 'contact_flash' and (effect.get('flash_scope') not in ('local', 'screen')
                    or effect['flash_scope'] == 'screen' and review.get('screen_flash_reviewed') is not True):
                raise ValueError('Explicit review required for a brief yellow screen flash')
            effect = {**copy.deepcopy(effect), 'automation': CONTRACT, 'asset_id': state['asset_id'], 'action_review': copy.deepcopy(review)}
            scene.setdefault('effects', []).append(effect)
    return result




def validate_frozen(timeline, sample, frame):
    accents = frame.get('action_accents') or []
    active = frame.get('active') or []
    if any(str(a).split(':')[0] in TYPES for a in active) and not accents:
        raise ValueError('Missing frozen attack source/timing review')
    if not isinstance(accents, list) or len(accents) > 6:
        raise ValueError('Unbounded attack accents')
    states = {s['asset_id']: s for s in timeline.get('states', [])}
    for accent in accents:
        state = states.get(sample.get('state')) or {}
        review = accent.get('review') or {}
        if (accent.get('type') not in TYPES or accent.get('asset_id') != sample.get('state')
                or not re_sha(accent.get('source_sha256')) or accent['source_sha256'] != state.get('sha256')
                or review.get('source_sha256') != state.get('sha256') or review.get('source_reviewed') is not True
                or review.get('contract') != CONTRACT):
            raise ValueError('Stale attack artwork review')
        contact, start, duration = (accent.get(k) for k in ('contact_at','from','duration_seconds'))
        if any(type(v) not in (int,float) or not math.isfinite(v) for v in (contact,start,duration)) or not 0 < duration <= TYPES[accent['type']]:
            raise ValueError('Invalid frozen contact timing')
        at = sample['at']
        if not start-1e-7 <= at < start+duration or (accent['type']=='attack_speedline' and (abs(start+duration-contact)>1e-6 or at>=contact)) or (accent['type']!='attack_speedline' and start<contact):
            raise ValueError('Attack effect violates travel/contact order')
        first, count = accent.get('shape_offset'), accent.get('shape_count')
        shapes = frame['overlays']
        if type(first) is not int or type(count) is not int or first<0 or count<0 or first+count>len(shapes):
            raise ValueError('Invalid frozen attack shape range')
        boxes = accent.get('protected_boxes')
        if not isinstance(boxes,list) or len(boxes)>100:
            raise ValueError('Missing frozen attack protection')
        wash = accent.get('protection_mode') == 'exposure_wash/v1'
        if wash:
            selected = shapes[first:first+count]
            if (accent['type'] != 'contact_flash' or review.get('screen_flash_reviewed') is not True
                    or len(selected) != 1 or selected[0].get('points') != [[0,0],[1920,0],[1920,1080],[0,1080]]
                    or selected[0].get('color') != '#fff7cf' or not 0 <= selected[0].get('opacity', 1) <= .22):
                raise ValueError('Invalid readable exposure wash')
        for b in boxes:
            if not isinstance(b,list) or len(b)!=4 or any(type(v) not in (int,float) or not math.isfinite(v) or not 0<=v<=1 for v in b) or b[0]>=b[2] or b[1]>=b[3]:
                raise ValueError('Invalid frozen attack protection')
            for shape in ([] if wash else shapes[first:first+count]):
                points=shape.get('points') or []
                if not points:raise ValueError('Attack vectors must retain their exact polygon geometry')
                bounds=[min(p[0] for p in points)/1920,min(p[1] for p in points)/1080,max(p[0] for p in points)/1920,max(p[1] for p in points)/1080]
                if bounds[0]<b[2] and bounds[2]>b[0] and bounds[1]<b[3] and bounds[3]>b[1]:
                    raise ValueError('Attack overlay covers a protected source region')


def re_sha(value):
    import re
    return isinstance(value,str) and re.fullmatch('[a-f0-9]{64}',value)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--package', required=True)
    parser.add_argument('--review', required=True)
    parser.add_argument('--source-root', required=True)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    output = Path(args.output)
    result = attach(json.loads(Path(args.package).read_text()), json.loads(Path(args.review).read_text()), args.source_root)
    with output.open('x', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
