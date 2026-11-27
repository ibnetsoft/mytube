"""Source-reviewed popup cut preparation on the existing shared PNG patch clock.

Run with python -m worker.wuxia_popup --help. No model calls or source rewrites.
"""
import argparse
import copy
import json
import math
from pathlib import Path
from PIL import Image, ImageDraw, ImageOps
from worker.ambient_loop import digest, pixel_box, validate

CONTRACT = 'wuxia_popup_plan/v1'


def enable_new_package(package, request=None):
    from worker.wuxia_narration import applies
    structure = package.setdefault('structure', {})
    if applies(request or {}) or structure.get('image_style') == 'wuxia_webtoon' or (structure.get('wuxia_ae_package') or {}).get('contract') == 'wuxia_still_ae_episode/v1':
        structure.setdefault('wuxia_popup_policy', dict(contract=CONTRACT, enabled=True,
            auto_prepare=True, max_per_episode=5, scenes_per_popup=6,
            intervening_scenes=2, minimum_gap_ms=20000, duration_ms=2200,
            exit_options=['fade', 'left', 'down', 'cut'],
            actual_source_review_required=True, zero_eligible_valid=True))
    return package


def prepare(package, plan, directory, upload=None):
    """Compile reviewed selections, enforcing episode-wide sparsity before writes.

    upload(path, content_key) returns (bucket, storage_path, media_url).
    Without upload the returned package is None; local placeholders cannot be registered.
    """
    scenes = package.get('scenes', [])
    cuts = plan.get('cuts')
    if plan.get('contract') != CONTRACT or not isinstance(cuts, list):
        raise ValueError('Invalid popup plan')
    if len(cuts) > min(5, len(scenes)//6):
        raise ValueError('Popup frequency exceeds one per six scenes or five per episode')
    result = copy.deepcopy(package)
    # Replacing existing prepared popup plans is explicit; do not silently accumulate.
    if any(l.get('popup_cut') for s in scenes for state in s.get('states', []) for l in state.get('ambient_loops', [])):
        raise ValueError('Package already contains popup cuts; preserve or explicitly remove the prior plan')
    jobs = []
    previous = -100
    last_end = -100000
    for cut in cuts:
        index = next((i for i,s in enumerate(scenes) if s.get('scene_id') == cut.get('scene_id')), -1)
        if index < 0 or index-previous < 3:
            raise ValueError('Popup cuts must be ordered with two intervening scenes')
        scene = result['scenes'][index]
        state = next((s for s in scene.get('states', []) if s.get('asset_id') == cut.get('state_asset_id')), None)
        if state is None or state.get('sha256') != cut.get('reviewed_source_sha256'):
            raise ValueError('Popup source review no longer matches the state')
        source = Path(cut.get('source_path', ''))
        if not source.is_file() or digest(source) != state['sha256']:
            raise ValueError('Popup actual source checksum mismatch')
        if cut.get('source_reviewed') is not True or not str(cut.get('reason', '')).strip() or not cut.get('protected_regions'):
            raise ValueError('Popup needs actual source review, narrative reason and face/text protection')
        start, duration = cut.get('start_ms'), cut.get('duration_ms', 2200)
        if type(start) is not int or type(duration) is not int or start < 0 or not 1800 <= duration <= 3200:
            raise ValueError('Popup needs a 1800-3200ms scene-local window')
        scene_start = scene.get('preview_start_seconds')
        scene_duration = scene.get('preview_duration_seconds')
        if not all(type(v) in (int,float) and math.isfinite(v) for v in (scene_start,scene_duration)) or scene_duration <= 0:
            raise ValueError('Popup needs an explicit scene clock')
        if not (state.get('start', 0)*scene_duration*1000 <= start and start+duration <= state.get('end', 1)*scene_duration*1000):
            raise ValueError('Popup window escapes its reviewed state exposure')
        absolute = scene_start*1000+start
        if absolute-last_end < 20000:
            raise ValueError('Popup cuts need at least 20 seconds between windows')
        crop = cut.get('crop')
        if not isinstance(crop,list) or len(crop)!=4 or not all(type(v) in (float,int) and math.isfinite(v) and 0<=v<=1 for v in crop) or not (crop[0]<crop[2] and crop[1]<crop[3]):
            raise ValueError('Invalid popup crop')
        if len(state.get('ambient_loops', [])) >= 4:
            raise ValueError('State patch capacity exceeded')
        with Image.open(source) as original:
            if original.format != 'PNG' or getattr(original,'n_frames',1)!=1:
                raise ValueError('Popup source must be a still PNG')
            width,height = original.size
        exit_style = cut.get('exit', 'fade')
        if exit_style not in ('fade', 'left', 'down', 'cut'):
            raise ValueError('Invalid popup exit option')
        panel_region = cut.get('region')
        # Validate the original panel before computing its full travel envelope.
        dummy = dict(media_url='https://prepared.invalid/popup.png',gcs_bucket='pending',gcs_path='pending',sha256='0'*64,duration_ms=60)
        loop = dict(contract='ambient_loop/v1',enabled=True,source_sha256=state['sha256'],role='environment',
                    width=width,height=height,region=cut.get('region'),protected_regions=cut['protected_regions'],
                    start_ms=start,end_ms=start+duration,phase_ms=0,repeat=False,frames=[dummy,dummy],
                    popup_cut=dict(contract=CONTRACT,reason=cut['reason'],crop=crop,source_reviewed=True))
        validate(loop)
        region = loop['region']
        if not .03 <= (region[2]-region[0])*(region[3]-region[1]) <= .20:
            raise ValueError('Popup panel must occupy 3-20 percent of the screen')
        box=pixel_box(region,(width,height))
        if min(box[2]-box[0],box[3]-box[1]) < 32:
            raise ValueError('Popup panel is too small')
        if exit_style == 'left' and region[0] > .15 or exit_style == 'down' and region[3] < .85:
            raise ValueError('Sliding exit must use a nearby screen edge')
        envelope = list(region)
        if exit_style == 'left': envelope[0] = 0
        if exit_style == 'down': envelope[3] = 1
        loop['region'] = envelope
        loop['popup_cut'].update(panel_region=panel_region, exit=exit_style)
        validate(loop)  # Entire exit path must also avoid protected regions.
        jobs.append((state,source,loop,crop,box,duration,exit_style))
        previous,last_end = index,absolute+duration
    directory=Path(directory);directory.mkdir(parents=True,exist_ok=True)
    manifests=[]
    for n,(state,source,loop,crop,box,duration,exit_style) in enumerate(jobs):
        target=directory/f'popup-{n+1:02d}';target.mkdir(exist_ok=True)
        with Image.open(source) as original:
            detail=original.convert('RGBA').crop(pixel_box(crop,original.size))
            if min(detail.size)<8:
                raise ValueError('Popup detail is too small to inspect')
            loop['frames']=[]
            # A quick entrance, a readable fixed hold, and optional edge exit.
            exit_ms = 320 if exit_style in ('left','down') else 240 if exit_style == 'fade' else 0
            holds = []
            remaining = duration-120-exit_ms
            while remaining:
                hold = min(2000,remaining);holds.append((1.,hold,0.,1.));remaining-=hold
            steps = [(.94,60,0.,1.),(.98,60,0.,1.)]+holds
            for j in range(exit_ms//40):
                progress = (j+1)/(exit_ms//40)
                steps.append((1.,40,progress if exit_style in ('left','down') else 0.,1-progress if exit_style=='fade' else 1.))
            for i,(scale,hold,travel,opacity) in enumerate(steps):
                w,h=box[2]-box[0],box[3]-box[1]
                pw,ph=round(w*scale),round(h*scale)
                panel=ImageOps.fit(detail,(pw,ph),method=Image.Resampling.LANCZOS)
                ImageDraw.Draw(panel).rectangle((0,0,pw-1,ph-1),outline='#e8e2d7',width=max(2,round(original.width/640)))
                if opacity < 1: panel.putalpha(panel.getchannel('A').point(lambda v:round(v*opacity)))
                patch=Image.new('RGBA',original.size)
                x,y=box[0]+(w-pw)//2,box[1]+(h-ph)//2
                if exit_style=='left': x-=round((box[2])*travel)
                if exit_style=='down': y+=round((height-box[1])*travel)
                patch.paste(panel,(x,y))
                path=target/f'frame-{i}.png';patch.save(path)
                sha=digest(path)
                frame=dict(sha256=sha,duration_ms=hold,local_path=str(path.resolve()),media_url='https://prepared.invalid/popup.png',gcs_bucket='pending',gcs_path='pending')
                if upload:
                    bucket,key,url=upload(path,sha+'.png')
                    frame.update(gcs_bucket=bucket,gcs_path=key,media_url=url)
                loop['frames'].append(frame)
        validate(loop)
        (target/'manifest.json').write_text(json.dumps(loop,ensure_ascii=False,indent=2),encoding='utf-8')
        manifests.append(loop)
        state.setdefault('ambient_loops',[]).append(loop)
    report=dict(contract=CONTRACT,status='prepared' if cuts else 'not_required',count=len(cuts),published=bool(upload),cuts=manifests)
    (directory/'popup-review.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    return (result if upload else None), report


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('package','plan','output'):
        p.add_argument('--'+name,type=Path,required=True)
    p.add_argument('--upload-prefix',help='Publish prepared files using configured GCS credentials')
    a=p.parse_args()
    upload=None
    if a.upload_prefix:
        import sys
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        from worker.ae_highlight_worker import _upload_gcs_file
        upload=lambda path,key:_upload_gcs_file(path,a.upload_prefix.rstrip('/')+'/'+key,'image/png')
    package,report=prepare(json.loads(a.package.read_text()),json.loads(a.plan.read_text()),a.output,upload)
    if package is not None:
        target=a.output/'package.with-popups.json'
        target.write_text(json.dumps(package,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({k:report[k] for k in ('status','count','published')}))

if __name__=='__main__':main()
