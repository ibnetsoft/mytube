"""Deterministic Motion Studio image/video compositor, shared by preview and final jobs."""
import bisect
import math
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageOps

EFFECTS = {'impact_shake','atmospheric_haze','warm_dust_motes','particle_burst','debris_burst',
           'focus_glow','light_sweep','impact_flash','shock_ring','energy_trail','subtle_vignette','speedline_burst'}

def validate_motion(value):
    if not isinstance(value, dict) or value.get('version') != 1 or not isinstance(value.get('enabled'), bool) or value.get('aspect') not in ('16:9','9:16') or value.get('fps') not in (24,30):
        raise ValueError('Invalid Motion Studio project')
    scenes=value.get('scenes')
    if not isinstance(scenes,dict) or len(scenes)>1000: raise ValueError('Invalid Motion Studio scene list')
    def number(v,lo,hi):
        if isinstance(v,bool) or not isinstance(v,(int,float)) or not math.isfinite(v) or not lo<=v<=hi: raise ValueError('Invalid Motion Studio numeric value')
    for identity,scene in scenes.items():
        if not isinstance(identity,str) or not identity.isdecimal() or int(identity)<1 or not isinstance(scene,dict): raise ValueError('Invalid scene number')
        if scene.get('source') not in ('auto','image','video','psd') or scene.get('fit') not in ('contain','cover') or scene.get('transition') not in ('cut','fade','flash','crossfade'): raise ValueError('Invalid source or transition')
        if scene.get('transition')=='crossfade': number(scene.get('transition_seconds',.22),.12,.6)
        if not isinstance(scene.get('direction'),str) or len(scene['direction'])>4000: raise ValueError('Invalid scene direction')
        keys=scene.get('keys')
        if not isinstance(keys,list) or not 2<=len(keys)<=64: raise ValueError('Invalid motion keys')
        previous=-1
        for key in keys:
            for field,lo,hi in [('t',0,1),('x',0,1),('y',0,1),('scale',1,2),('rotation',-8,8),('opacity',0,100)]: number(key.get(field),lo,hi)
            if key['t']<=previous: raise ValueError('Unordered motion keys')
            previous=key['t']
        if keys[0]['t']!=0 or keys[-1]['t']!=1: raise ValueError('Incomplete motion timeline')
        effects=scene.get('effects')
        if not isinstance(effects,list) or len(effects)>len(EFFECTS) or len({e.get('type') for e in effects})!=len(effects): raise ValueError('Invalid effect list')
        for effect in effects:
            if effect.get('type') not in EFFECTS: raise ValueError('Unsupported Motion Studio effect')
            for field,lo,hi in [('start',0,1),('end',0,1),('intensity',.05,1),('radius',.02,1)]: number(effect.get(field),lo,hi)
            if effect['end']<=effect['start']: raise ValueError('Invalid effect window')
            for field,length in [('center',2),('color',3)]:
                if not isinstance(effect.get(field),list) or len(effect[field])!=length: raise ValueError('Invalid effect coordinates')
                for item in effect[field]: number(item,0,1)
    return value

def pose_at(keys,t):
    for a,b in zip(keys,keys[1:]):
        if a['t']<=t<=b['t']:
            f=(t-a['t'])/(b['t']-a['t'])
            return {k:a[k]+(b[k]-a[k])*f for k in ('x','y','scale','rotation','opacity')}
    return keys[-1]

def compose_frame(image,scene,t,resolution):
    w,h=resolution
    p=pose_at(scene['keys'],t)
    scale=(max(w/image.width,h/image.height) if scene['fit']=='cover' else min(w/image.width,h/image.height))*p['scale']
    # Inverse affine mapping avoids allocating huge intermediate canvases for tall PSD exports.
    theta=math.radians(p['rotation']);c,s=math.cos(theta)/scale,math.sin(theta)/scale
    cx,cy=image.width*p['x'],image.height*p['y']
    frame=image.convert('RGB').transform((w,h),Image.Transform.AFFINE,(c,s,cx-c*w/2-s*h/2,-s,c,cy+s*w/2-c*h/2),Image.Resampling.BICUBIC,fillcolor='#0c1018').convert('RGBA')
    if p['opacity']<100: frame=Image.blend(Image.new('RGBA',(w,h),'#0c1018'),frame,p['opacity']/100)
    for e in scene['effects']:
        if not e['start']<=t<=e['end']:continue
        u=(t-e['start'])/(e['end']-e['start']); strength=e['intensity']*min(1,u/.15,(1-u)/.3)
        cx,cy=e['center'][0]*w,e['center'][1]*h;r=e['radius']*min(w,h)
        color=tuple(round(v*255) for v in e['color']); kind=e['type']
        overlay=Image.new('RGBA',(w,h));d=ImageDraw.Draw(overlay)
        if kind=='impact_shake':
            # Shake the final camera viewport with overscan, preserving overlay registration.
            ax=w*.008*strength*math.sin(u*math.pi*10);ay=h*.006*strength*math.cos(u*math.pi*10)
            frame=frame.transform((w,h),Image.Transform.AFFINE,(.97,0,w*.015+ax,0,.97,h*.015+ay),Image.Resampling.BICUBIC)
        elif kind=='shock_ring':
            radius=max(1,r*(.1+u));d.ellipse((cx-radius,cy-radius*.65,cx+radius,cy+radius*.65),outline=(*color,round(220*strength)),width=max(1,round(w*.004)))
        elif kind in ('particle_burst','debris_burst','warm_dust_motes'):
            for i in range(22 if kind!='debris_burst' else 12):
                angle=i*2.399963;dist=r*(.2+(i%5)*.15)*(u if kind!='warm_dust_motes' else 1)
                x=cx+math.cos(angle)*dist;y=cy+math.sin(angle)*dist-(u*h*.04 if kind=='warm_dust_motes' else 0);size=max(1,w*(.007 if kind=='debris_burst' else .0025))
                if kind=='debris_burst':d.polygon([(x-size,y),(x,y-size),(x+size,y+size)],fill=(*color,round(220*strength)))
                else:d.ellipse((x-size,y-size,x+size,y+size),fill=(*color,round(180*strength)))
        elif kind=='speedline_burst':
            for i in range(24):
                a=i*math.pi/12;d.line([(cx+math.cos(a)*r*.45,cy+math.sin(a)*r*.45),(cx+math.cos(a)*r*1.8,cy+math.sin(a)*r*1.8)],fill=(*color,round(130*strength)),width=max(1,round(w*.002)))
        elif kind=='energy_trail':
            points=[(cx-r*.8,cy+r*.35),(cx-r*.16,cy-r*.42),(cx+r*.18,cy+r*.1),(cx+r*.9,cy-r*.32)]
            d.line(points[:max(2,min(4,2+int(u*3)))],fill=(*color,round(220*strength)),width=max(2,round(w*.005)),joint='curve')
        elif kind=='subtle_vignette':
            d.rectangle((0,0,w,h),fill=(0,0,0,round(80*strength)));d.ellipse((w*.04,h*.04,w*.96,h*.96),fill=(0,0,0,0));overlay=overlay.filter(ImageFilter.GaussianBlur(min(w,h)*.1))
        else:
            if kind=='light_sweep':cx=(.2+.6*u)*w
            if kind=='impact_flash':d.rectangle((0,0,w,h),fill=(*color,round(110*strength)))
            else:
                alpha=45 if kind=='atmospheric_haze' else 65
                d.ellipse((cx-r,cy-r,cx+r,cy+r),fill=(*color,round(alpha*strength)));overlay=overlay.filter(ImageFilter.GaussianBlur(max(1,r*.25)))
        frame=Image.alpha_composite(frame,overlay)
    if t<.08 and scene['transition']!='cut':
        frame=Image.blend(Image.new('RGBA',(w,h),'white' if scene['transition']=='flash' else 'black'),frame,t/.08)
    return np.asarray(frame.convert('RGB'))

class MotionFrames:
    def __init__(self,images,durations,subtitles,settings,resolution,font_path,scene_numbers=None):
        from services.comic_render_service import build_timeline
        from services.comic_lettering import caption_layers
        self.options=validate_motion(settings['motion']);self.mode='motion_studio';self.turn=0;self.resolution=resolution
        if (resolution[0]<resolution[1])!=(self.options['aspect']=='9:16'):raise ValueError('Motion Studio output aspect mismatch')
        self.starts,self.pages,self.duration=build_timeline(durations,1,0,{},'single')
        self.paths=images;self.numbers=scene_numbers or list(range(1,len(images)+1));self._current=-1;self._media=None;self._clip=None;self._still_frame=None
        self._last_scene_index=-1;self._last_scene_frame=None;self._transition_source=None;self.balloons=[]
        for i in range(len(images)):
            blocks=[s for s in subtitles if self.starts[i]<=float(s.get('start',s.get('start_time',0)))<self.starts[i+1]]
            self.balloons.append(caption_layers(resolution,blocks,font_path,max(12,round(32*resolution[0]/1280)),'bottom'))
    def close(self):
        self._still_frame=None
        if self._clip:self._clip.close();self._clip=None
        if self._media:self._media.close();self._media=None
    def page(self,index,source_time,all_balloons=False):
        if self._current!=index:
            self.close();path=self.paths[index]
            if Path(path).suffix.lower() in ('.mp4','.mov','.webm','.mkv','.m4v','.avi'):
                from moviepy import VideoFileClip
                self._clip=VideoFileClip(path,audio=False)
                from services.video_playback_policy import require_video_duration
                require_video_duration(self._clip.duration,self.starts[index+1]-self.starts[index],self._clip.fps,self.numbers[index])
            else:
                with Image.open(path) as source:self._media=ImageOps.exif_transpose(source).convert('RGB')
            self._current=index
        local=max(0,source_time-self.starts[index]);duration=self.starts[index+1]-self.starts[index]
        scene=self.options['scenes'].get(str(self.numbers[index]),{'source':'auto','fit':'contain','keys':[dict(t=t,x=.5,y=.5,scale=1,rotation=0,opacity=100) for t in (0,1)],'effects':[],'transition':'cut'})
        if scene['source']=='psd':scene={**scene,'fit':'contain','keys':[dict(t=t,x=.5,y=.5,scale=1,rotation=0,opacity=100) for t in (0,1)],'effects':[],'transition':'cut'}
        render_scene={**scene,'transition':'cut'} if scene['transition']=='crossfade' else scene
        # Static original images need one affine composition, not one per output frame.
        # Time-dependent effects, transitions and captions always take the original path.
        still=not self._clip and not self.balloons[index] and not render_scene['effects'] and render_scene['transition']=='cut' and all(
            all(key[field]==render_scene['keys'][0][field] for field in ('x','y','scale','rotation','opacity')) for key in render_scene['keys'])
        if still and self._still_frame is not None:return self._still_frame
        image=Image.fromarray(self._clip.get_frame(min(local,max(0,self._clip.duration-1/max(1,self._clip.fps))))) if self._clip else self._media
        canvas=Image.fromarray(compose_frame(image,render_scene,min(1,local/duration),self.resolution)).convert('RGBA')
        self._last_scene_frame=np.asarray(canvas.convert('RGB')).copy()
        for start,layer,position in self.balloons[index]:
            if all_balloons or source_time>=start:canvas.alpha_composite(layer,position)
        result=np.asarray(canvas.convert('RGB'))
        if still:self._still_frame=result
        return result
    def frame(self,t):
        index=min(len(self.pages)-1,max(0,bisect.bisect_right(self.starts,t)-1))
        if index!=self._last_scene_index:
            self._transition_source=self._last_scene_frame.copy() if index>0 and self._last_scene_frame is not None else None
            self._last_scene_index=index
        frame=self.page(index,t)
        scene=self.options['scenes'].get(str(self.numbers[index]),{})
        local=max(0,t-self.starts[index]);transition_seconds=float(scene.get('transition_seconds',.22))
        if scene.get('transition')=='crossfade' and self._transition_source is not None and local<transition_seconds:
            alpha=min(1,max(0,local/transition_seconds))
            frame=np.asarray(np.asarray(self._transition_source,dtype='float32')*(1-alpha)+np.asarray(frame,dtype='float32')*alpha,dtype='uint8')
        return frame

def render_motion(*,temp_dir,images,durations,audio_path,subtitles,settings,resolution,scene_numbers=None,sfx_cues=None,progress_callback=None,template_overlay_path=None):
    from moviepy import VideoClip
    from services.ffmpeg_slideshow_service import render_ffmpeg_slideshow
    import hashlib
    import json
    progress=progress_callback or (lambda *_:None)
    motion=validate_motion(settings['motion'])
    frames=MotionFrames(images,durations,[],settings,resolution,'',scene_numbers)
    visual=Path(temp_dir)/'motion-visual.mp4';clip=None
    try:
        progress(35,'Motion Studio 카메라·효과 프레임 렌더링')
        clip=VideoClip(frames.frame,duration=frames.duration)
        clip.write_videofile(str(visual),fps=motion['fps'],codec='libx264',audio=False,preset='veryfast',threads=2,logger=None,ffmpeg_params=['-pix_fmt','yuv420p','-movflags','+faststart'])
    finally:
        if clip:clip.close()
        frames.close()
    # Use the production caption/audio compositor so saved fonts, BGM ranges,
    # narration, SFX and template overlays have the same meaning in every mode.
    output=render_ffmpeg_slideshow(temp_dir=temp_dir,images=[str(visual)],audio_path=audio_path,
        durations=[sum(durations)],subtitles=subtitles,subtitle_settings=settings,image_effects=['none'],
        transition_effects=['none'],resolution=resolution,template_overlay_path=template_overlay_path,
        sfx_cues=sfx_cues,progress_callback=progress)
    def sha(path):
        h=hashlib.sha256()
        with Path(path).open('rb') as handle:
            for block in iter(lambda:handle.read(1024*1024),b''):h.update(block)
        return h.hexdigest()
    manifest={'contract':'motion_render_manifest/v1','motion':motion,'scene_numbers':scene_numbers,
        'source_sha256':[sha(path) for path in images],'audio_sha256':sha(audio_path),
        'render_sha256':sha(output),'duration':sum(durations),'resolution':resolution,
        'review_status':'rendered_not_automatically_approved'}
    (Path(temp_dir)/'motion_manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
    return output
