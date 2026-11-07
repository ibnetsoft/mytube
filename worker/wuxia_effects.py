"""Validate frozen web effect samples before native AE consumes them verbatim."""
import math
import re


def validate_samples(timeline):
    samples=timeline.get('samples') or []
    if any(s.get('effects',{}).get('active') for s in samples) and timeline.get('contract') not in ('wuxia_native_timeline/v3','wuxia_native_timeline/v4'):
        raise ValueError('Wuxia impacts require v3; never silently omit effects')
    for sample in samples:
        f=sample.get('effects')
        if f is None:
            if timeline.get('contract') in ('wuxia_native_timeline/v3','wuxia_native_timeline/v4'):raise ValueError('Missing frozen effect sample')
            continue
        if f == {}:continue # Explicit identity frame; missing v3 fields still fail above.
        def number(v,lo,hi):return type(v) in (int,float) and math.isfinite(v) and lo<=v<=hi
        if (f.get('contract')!='wuxia_effect_samples/v1' or f.get('issues')!=[]
                or not number(f.get('dx'),-20,20) or not number(f.get('dy'),-12,12)
                or not number(f.get('scale'),1,1.04)):
            raise ValueError('Invalid or unsafe frozen impact transform')
        shapes=f.get('overlays')
        if not isinstance(shapes,list) or len(shapes)>96:raise ValueError('Unbounded impact overlay')
        for q in shapes:
            if (q.get('kind') not in ('ellipse','polygon','line') or not re.fullmatch(r'#[0-9a-fA-F]{6}',str(q.get('color')))
                    or not number(q.get('opacity'),0,1)):
                raise ValueError('Invalid impact vector')
            if q['kind']=='ellipse':
                if not all(number(q.get(k),lo,hi) for k,lo,hi in [('cx',-1920,3840),('cy',-1080,2160),('rx',0,1920),('ry',0,1080),('stroke',0,6)]):raise ValueError('Invalid impact ellipse')
            else:
                points=q.get('points')
                if (not isinstance(points,list) or not 2<=len(points)<=4
                        or any(not isinstance(p,list) or len(p)!=2 or not number(p[0],-1920,3840) or not number(p[1],-1080,2160) for p in points)):
                    raise ValueError('Invalid impact points')
                if q['kind']=='line' and not number(q.get('width'),.1,6):raise ValueError('Invalid impact stroke')
