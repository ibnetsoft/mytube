"""Prepared ambient patches: shared editor/native timing, no source-video retiming."""
from __future__ import annotations
import hashlib
import json
import math
from pathlib import Path
from PIL import Image

CONTRACT = 'ambient_loop/v1'

def digest(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()

def validate(loop):
    def number(v, lo, hi):
        return type(v) in (int, float) and math.isfinite(v) and lo <= v <= hi
    def sha(v):
        return isinstance(v, str) and len(v) == 64 and all(c in '0123456789abcdef' for c in v)
    def rect(r):
        return isinstance(r, list) and len(r) == 4 and all(number(v, 0, 1) for v in r) and r[0] < r[2] and r[1] < r[3]
    r = loop.get('region')
    protected = loop.get('protected_regions')
    if (loop.get('contract') != CONTRACT or type(loop.get('enabled')) is not bool
        or type(loop.get('width')) is not int or type(loop.get('height')) is not int
        or not 1<=loop['width']<=8192 or not 1<=loop['height']<=8192 or loop['width']*loop['height']>16000000
        or not sha(loop.get('source_sha256')) or loop.get('role') not in ('background','hair','cloth','environment')
        or not rect(r) or (r[2]-r[0])*(r[3]-r[1]) > .35 or not isinstance(protected, list) or len(protected)>100
        or any(not rect(p) or (r[0]<p[2] and r[2]>p[0] and r[1]<p[3] and r[3]>p[1]) for p in protected)
        or not number(loop.get('start_ms'),0,3600000) or not number(loop.get('end_ms'),loop['start_ms']+1,3600000)
        or not number(loop.get('phase_ms'),0,3600000) or type(loop.get('repeat')) is not bool):
        raise ValueError('Invalid ambient loop or protected-region overlap')
    frames = loop.get('frames')
    if not isinstance(frames,list) or not 2 <= len(frames) <= 16:
        raise ValueError('Ambient loop needs 2-16 prepared frames')
    for f in frames:
        if (not sha(f.get('sha256')) or type(f.get('duration_ms')) is not int or not 20 <= f['duration_ms'] <= 2000
            or not isinstance(f.get('media_url'),str) or not f['media_url'].startswith(('https://','/api/std/'))
            or not isinstance(f.get('gcs_bucket'),str) or not f['gcs_bucket'] or not isinstance(f.get('gcs_path'),str) or not f['gcs_path']):
            raise ValueError('Invalid prepared ambient frame')
    if 'sword_aura' in loop:
        from worker.wuxia_sword_aura import validate_contract
        validate_contract(loop)
    return loop

def frame_index(loop, local_ms):
    validate(loop)
    if not loop['enabled'] or not math.isfinite(local_ms): return None
    ms = math.floor(local_ms + 1e-6)
    if ms < loop['start_ms'] or ms >= loop['end_ms']: return None
    total = sum(f['duration_ms'] for f in loop['frames'])
    at = ms - loop['start_ms'] + loop['phase_ms']
    at = at % total if loop['repeat'] else min(at, total-1)
    for i,f in enumerate(loop['frames']):
        if at < f['duration_ms']: return i
        at -= f['duration_ms']


def pixel_box(region, size):
    # Conservative: do not paint a pixel that straddles the protected boundary.
    w,h = size
    return (math.ceil(region[0]*w),math.ceil(region[1]*h),math.floor(region[2]*w),math.floor(region[3]*h))


def prepare_gif(source, gif, directory, *, region, protected_regions, role, end_ms, start_ms=0, phase_ms=0, repeat=True):
    """Pillow resolves GIF disposal. Only the approved ROI survives in each PNG."""
    directory=Path(directory);directory.mkdir(parents=True,exist_ok=True)
    with Image.open(source) as base:
        if base.format != 'PNG' or getattr(base,'n_frames',1)!=1: raise ValueError('Base must be a fixed PNG')
        size=base.size
        if size[0]*size[1] > 16_000_000: raise ValueError('Ambient canvas too large')
        base.save(directory/'poster.png')
    loop=dict(contract=CONTRACT,enabled=True,width=size[0],height=size[1],source_sha256=digest(source),role=role,region=region,
              protected_regions=protected_regions,start_ms=start_ms,end_ms=end_ms,phase_ms=phase_ms,repeat=repeat,frames=[])
    # Validate geometry before decoding/writing generated pixels.
    dummy=dict(media_url='https://prepared.invalid/frame.png',gcs_bucket='pending',gcs_path='pending',sha256='0'*64,duration_ms=100)
    validate({**loop,'frames':[dummy,dummy]})
    box=pixel_box(region,size)
    if box[2]<=box[0] or box[3]<=box[1]: raise ValueError('Ambient region smaller than one pixel')
    with Image.open(gif) as animation:
        if animation.format!='GIF' or animation.size!=size or not 2<=animation.n_frames<=16: raise ValueError('GIF canvas or frame count mismatch')
        for index in range(animation.n_frames):
            animation.seek(index)
            duration=animation.info.get('duration')
            if type(duration) is not int or not 20<=duration<=2000: raise ValueError('GIF needs explicit frame durations (20-2000ms)')
            patch=Image.new('RGBA',size)
            resolved=animation.convert('RGBA')
            patch.paste(resolved.crop(box),box)
            path=directory/f'frame-{index:03d}.png';patch.save(path)
            loop['frames'].append({**dummy,'duration_ms':duration,'sha256':digest(path),'local_path':path.name})
    loop['gif_sha256']=digest(gif)
    (directory/'manifest.local.json').write_text(json.dumps(loop,ensure_ascii=False,indent=2),encoding='utf-8')
    return loop


def prepare_runtime(source, loops, directory, fresh, download):
    """Frozen submission only. Hash + actual alpha envelope checked before AE import."""
    if not loops: return []
    if not isinstance(loops,list) or len(loops)>4: raise ValueError('Too many ambient loops')
    directory=Path(directory);directory.mkdir(parents=True,exist_ok=True)
    with Image.open(source) as original: size=original.size
    source_hash=digest(source);result=[]
    for loop in loops:
        validate(loop)
        if (loop['width'],loop['height'])!=size:raise ValueError('Ambient manifest canvas mismatch')
        if loop['source_sha256']!=source_hash: raise ValueError('Ambient base image changed')
        files=[];box=pixel_box(loop['region'],size)
        for f in loop['frames']:
            fresh();path=directory/(f['sha256']+'.png')
            if not path.exists() or digest(path)!=f['sha256']: download(f,path)
            if digest(path)!=f['sha256']: raise ValueError('Ambient frame checksum mismatch')
            with Image.open(path) as image:
                if image.format!='PNG' or getattr(image,'n_frames',1)!=1 or image.size!=size or image.mode!='RGBA': raise ValueError('Ambient frame canvas/alpha mismatch')
                alpha=image.getchannel('A');bounds=alpha.getbbox()
                if 'sword_aura' in loop:
                    from worker.wuxia_sword_aura import validate_alpha
                    validate_alpha(loop,alpha)
                if bounds and (bounds[0]<box[0] or bounds[1]<box[1] or bounds[2]>box[2] or bounds[3]>box[3]):
                    raise ValueError('Ambient pixels escaped the approved region')
            files.append(str(path.resolve()))
        result.append({**loop,'files':files})
    return result


def jsx(runtime, duration, fps):
    """Sample the same millisecond clock at final output frames; HOLD, never blend."""
    count=math.ceil(duration*fps)
    if count>108000: raise ValueError('Ambient timeline too large')
    data=[]
    for loop in runtime:
        times=[[] for _ in loop['frames']];previous=None
        for index in range(count):
            current=frame_index(loop,index/fps*1000)
            if current!=previous:
                if previous is not None: times[previous].append([index/fps,0])
                if current is not None: times[current].append([index/fps,100])
                previous=current
        data.append({'files':loop['files'],'keys':times})
    return '''
    // Prepared ambient patches sit below subsequent authored lettering/effects.
    var AMBIENT='''+json.dumps(data,ensure_ascii=True,allow_nan=False)+''';
    for(var ai=0;ai<AMBIENT.length;ai++)for(var fi=0;fi<AMBIENT[ai].files.length;fi++){
      var af=app.project.importFile(new ImportOptions(new File(AMBIENT[ai].files[fi])));
      if(af.width!==W||af.height!==H)throw new Error('Ambient canvas mismatch');
      var al=source.layers.add(af);al.name='ambient_'+ai+'_'+fi;al.outPoint=S.duration;
      var ao=al.property('ADBE Transform Group').property('ADBE Opacity');ao.setValueAtTime(0,0);
      var ak=AMBIENT[ai].keys[fi];for(var ki=0;ki<ak.length;ki++)ao.setValueAtTime(ak[ki][0],ak[ki][1]);
      for(var ki=1;ki<=ao.numKeys;ki++)ao.setInterpolationTypeAtKey(ki,KeyframeInterpolationType.HOLD,KeyframeInterpolationType.HOLD);
    }
'''
