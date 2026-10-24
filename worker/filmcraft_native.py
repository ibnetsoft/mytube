"""Source media, editable keys/graphics/captions, native audio and verified GPU exports."""
from __future__ import annotations
import json
import math
import re
import shutil
import os
from functools import lru_cache
from pathlib import Path

from scripts.filmcraft import sha
from filmcraft_render import PIN, CONTRACT, VERSION, TICKS, binary, execute

EFFECTS=frozenset(CONTRACT['effects'])


@lru_cache(maxsize=32)
def font_coverage(family):
    """Check the selected face itself; never approve missing-glyph squares."""
    from fontTools.ttLib import TTFont, TTCollection
    roots=[Path(os.environ.get('WINDIR','C:/Windows'))/'Fonts',
           Path(os.environ.get('LOCALAPPDATA',str(Path.home())))/'Microsoft/Windows/Fonts',
           Path('/usr/share/fonts'),Path.home()/'.local/share/fonts',Path('/Library/Fonts')]
    coverage=set()
    for root in roots:
        if not root.is_dir():continue
        for path in root.rglob('*'):
            if path.suffix.lower() not in ('.ttf','.otf','.ttc','.otc'):continue
            fonts=[]
            try:
                fonts=TTCollection(path,lazy=True).fonts if path.suffix.lower() in ('.ttc','.otc') else [TTFont(path,lazy=True)]
                for font in fonts:
                    names={n.toUnicode().casefold() for n in font['name'].names if n.nameID in (1,16)}
                    if family.casefold() in names:coverage.update(font.getBestCmap() or {})
            except (OSError,ValueError):continue
            finally:
                for font in fonts:font.close()
    if not coverage:raise ValueError('Cannot verify native subtitle font coverage: '+family)
    return frozenset(coverage)


def validate_caption_glyphs(family,rows):
    coverage=font_coverage(family)
    missing=sorted({c for row in rows for c in str(row.get('text','')) if not c.isspace() and ord(c) not in coverage})
    if missing:raise ValueError('Selected native subtitle font '+family+' lacks glyphs: '+''.join(missing[:32]))


def caption_commands(rows,fps):
    # The engine floors start but rounds duration separately. Quantize shared
    # absolute boundaries first so contiguous recorded subtitles cannot overlap.
    commands=[];previous_end=-1
    for row in sorted(rows,key=lambda r:r['start']):
        if not row.get('text') or row['end']<=row['start']:continue
        start=math.ceil(float(row['start'])*fps-1e-8)
        end=math.ceil(float(row['end'])*fps-1e-8)
        if start<previous_end or end<=start:raise ValueError('Native captions overlap or are shorter than one frame')
        commands.append(('captions.add',{'track':'C1','text':str(row['text']),
            'time':start*(TICKS//fps),'durationSeconds':(end-start)/fps}))
        previous_end=end
    return commands


def cache_is_current(record):
    """A reviewed video alone is insufficient: the editable execution and AI inputs must match."""
    try:
        project=Path(record['filmcraft_project'])
        if not project.is_file() or sha(project)!=record.get('filmcraft_project_sha256'):return False
        receipt=Path(record['filmcraft_receipt'])
        if not receipt.is_file() or sha(receipt)!=record.get('filmcraft_receipt_sha256'):return False
        data=json.loads(receipt.read_text(encoding='utf-8'))
        gpu=data.get('gpu_composition') or {}
        if data.get('adapter')!=VERSION or gpu.get('compositedFrames',0)<=0:return False
        if (gpu.get('adapter') or {}).get('deviceType') not in ('DiscreteGpu','IntegratedGpu','VirtualGpu'):return False
        if record.get('filmcraft_ai_source'):
            source=Path(record['filmcraft_ai_source'])
            if not source.is_file() or sha(source)!=record.get('filmcraft_ai_sha256'):return False
        return True
    except (KeyError,OSError,TypeError,ValueError):return False


def ticks(seconds):
    value=float(seconds)
    if not math.isfinite(value) or abs(value)>86400:raise ValueError('Invalid FilmCraft time')
    return round(value*TICKS)


def pose_at(keys,t):
    if t<=keys[0]['t']:return keys[0]
    for a,b in zip(keys,keys[1:]):
        if t<=b['t']:
            f=(t-a['t'])/(b['t']-a['t'])
            return {k:a[k]+(b[k]-a[k])*f for k in ('x','y','scale','rotation','opacity')}
    return keys[-1]


def pulse(u):return max(0,min(1,u/.15,(1-u)/.3))


def color(value,alpha=None):
    if isinstance(value,str):
        raw=value.lstrip('#')
        if len(raw)==3:raw=''.join(c*2 for c in raw)
        if not re.fullmatch('[0-9a-fA-F]{6}([0-9a-fA-F]{2})?',raw):raise ValueError('Invalid native color')
        if alpha is None:alpha=int(raw[6:8],16)/255 if len(raw)==8 else 1
        return '#'+raw[:6]+f'{round(max(0,min(1,alpha))*255):02x}'
    if len(value)!=3 or any(not math.isfinite(v) or not 0<=v<=1 for v in value):raise ValueError('Invalid native color')
    return '#'+''.join(f'{round(v*255):02x}' for v in value)+f'{round(max(0,min(1,1 if alpha is None else alpha))*255):02x}'


def validate_scene(snapshot,scene,plan):
    if snapshot.get('renderer',{}).get('revision')!=PIN['revision']:raise ValueError('FilmCraft frozen source revision mismatch')
    if snapshot.get('renderer',{}).get('adapter') not in (None,VERSION):raise ValueError('FilmCraft native adapter contract mismatch')
    if scene['source_kind'] not in ('image','video'):raise ValueError('FilmCraft requires original image/video sources; PSD must be prepared as video')
    if snapshot['motion'].get('web') or any(plan.get(k) for k in ('native','finance','cues','layers')):
        raise ValueError('FilmCraft cannot discard browser rigs or PSD layer contracts')
    unknown={e['type'] for e in plan.get('effects',[])}-EFFECTS
    if unknown:raise ValueError('Unsupported native FilmCraft effects: '+', '.join(sorted(unknown)))
    if plan.get('transition') not in ('cut','fade','flash','crossfade'):raise ValueError('Unsupported native transition')


class NativeTimeline:
    def __init__(self,directory,fps,size,duration,fresh):
        self.directory=Path(directory).resolve();self.directory.mkdir(parents=True,exist_ok=True)
        self.fps=fps;self.size=tuple(size);self.duration=duration;self.fresh=fresh
        self.cli=binary();self.project=self.directory/'timeline.fcproj';self.output=self.directory/'filmcraft.mp4'
        self.counter=0;self.media={};self.inputs=[];self.scene_clips=[];self.sfx_ends=[]
        for path in (self.project,self.output):
            if path.exists():
                old=path.with_name(path.stem+'-'+sha(path)[:16]+'.previous'+path.suffix)
                if not old.exists():shutil.copy2(path,old)
        self.call('file.newSequence',{'name':'AIR native FilmCraft','width':size[0],'height':size[1],
            'fps':fps,'video':128,'audio':128},new=True)
        self.batch([('prefs.set',{'key':'media.importImageSequences','value':False})])
        self.background_clip=self.shape('rectangle',(size[0]/2,size[1]/2),size,0,duration,'#0c1018',track=0)

    def run(self,args,stage):
        self.fresh();self.counter+=1
        return execute(self.cli,args,self.directory,f'{self.counter:04d}-{stage}')

    def call(self,name,params,new=False):
        args=['--save-as',self.project] if new else ['--project',self.project,'--save']
        return self.run([*args,'exec',name,json.dumps(params,ensure_ascii=False,allow_nan=False)],name.replace('.','-'))

    def batch(self,commands):
        if not commands:return
        script=self.directory/f'commands-{self.counter+1:04d}.jsonl'
        script.write_text(''.join(json.dumps({'id':name,'params':params},ensure_ascii=False,allow_nan=False)+'\n' for name,params in commands),encoding='utf-8')
        self.run(['--project',self.project,'--save','run',script],'commands')

    def param(self,clip,effect,param,value,time=None):
        p={'clip':clip,'effect':effect,'param':param,'value':value}
        if time is not None:p.update(time=ticks(time),keyframe=True)
        return 'effects.setParam',p

    def import_media(self,path):
        path=Path(path).resolve()
        if path in self.media:return self.media[path]
        if not path.is_file():raise ValueError('FilmCraft source missing: '+str(path))
        info=self.run(['probe',path],'probe')
        result=self.call('file.import',{'paths':[str(path)],'imageSequence':False})
        if len(result.get('items',[]))!=1 or result.get('errors'):raise ValueError('Native source import failed')
        item=result['items'][0];self.media[path]=(item,info)
        self.inputs.append({'path':str(path),'sha256':sha(path),'item':item,'kind':info['kind']})
        return item,info

    def place(self,path,start,duration,track='V2',source_in=0,audio=False):
        item,info=self.import_media(path)
        result=self.call('timeline.place',{'item':item,'track':track,'time':ticks(start),
            'sourceIn':ticks(source_in),'duration':ticks(duration),'video':track.startswith('V'),'audio':audio})
        if len(result.get('clips',[]))!=1:raise ValueError('Expected a single native track clip')
        return result['clips'][0],info

    def shape(self,kind,position,size,start,duration,fill,*,track=None,props=None):
        p={'shape':kind,'position':position,'size':size,'time':ticks(start),'seconds':duration}
        if track is not None:p['track']=track
        clip=self.call('graphics.newShape',p)['clip']
        self.call('graphics.set',{'clip':clip,'props':{'fill_color':color(fill),**(props or {})}})
        return clip

    def animate(self,clip,effect,param,keys):
        self.batch([self.param(clip,effect,param,value,t) for t,value in keys])

    def source_scene(self,scene,plan,source,start,ai_source=None):
        duration=scene['end']-scene['start'];w,h=self.size
        clip,info=self.place(source,start,duration)
        video=info.get('video') or {};sw=video.get('width');sh=video.get('height')
        if not sw or not sh:raise ValueError('Native video dimensions missing')
        if video.get('par') not in (None,[1,1]):raise ValueError('Review non-square-pixel footage before native FilmCraft submission')
        if scene['source_kind']=='video' and info.get('duration',0)/TICKS+1/self.fps<duration:
            raise ValueError('Native source video is shorter than the finalized scene; prepare an explicit held tail')
        base=(max if plan['fit']=='cover' else min)(w/sw,h/sh)
        times={k['t'] for k in plan['keys']}
        for e in plan.get('effects',[]):
            if e['type']=='impact_shake':
                times.update(e['start']+(e['end']-e['start'])*i/64 for i in range(65))
                # Isolate overscan to its cue instead of interpolating it across the whole scene.
                epsilon=1/(duration*self.fps)
                times.update((max(0,e['start']-epsilon),min(1,e['end']+epsilon)))
        if plan['transition']=='fade':times.add(.08)
        commands=[]
        for t in sorted(times):
            pose=pose_at(plan['keys'],t);scale=base*pose['scale'];x=y=0
            for e in plan.get('effects',[]):
                if e['type']=='impact_shake' and e['start']<=t<=e['end']:
                    u=(t-e['start'])/(e['end']-e['start']);strength=e['intensity']*pulse(u)
                    scale/=.97;x-=w*.008*strength*math.sin(u*math.pi*10)/.97;y-=h*.006*strength*math.cos(u*math.pi*10)/.97
            at=start+t*duration
            for param,value in [('position',[w/2+x,h/2+y]),('anchor',[sw*pose['x'],sh*pose['y']]),
                ('scale',100*scale),('rotation',pose['rotation'])]:commands.append(self.param(clip,'motion',param,value,at))
            opacity=pose['opacity']*(min(1,t/.08) if plan['transition']=='fade' else 1)
            commands.append(self.param(clip,'opacity','opacity',opacity,at))
        self.batch(commands)
        if plan['transition']=='crossfade':
            self.call('sequence.applyVideoTransition',{'clip':clip,'edge':'in','effect':'cross_dissolve',
                'frames':max(1,round(plan.get('transition_seconds',.22)*self.fps))})
        if plan['transition']=='flash':
            flash=self.shape('rectangle',(w/2,h/2),(w,h),start,min(.08,duration),'#ffffff')
            self.animate(flash,'graphic_shape','opacity',[(start,100),(start+min(.08,duration),0)])
        for e in plan.get('effects',[]):self.effect(e,start,duration)
        if ai_source:
            ai=scene['_native_ai_plan'];at=start+ai['start'];length=ai['duration']
            overlay,probe=self.place(ai_source,at,length,track='V127')
            vw,vh=probe['video']['width'],probe['video']['height']
            if probe['duration']/TICKS+1/self.fps<length:raise ValueError('AI insert is shorter than its reviewed interval')
            self.batch([self.param(overlay,'motion','scale',100*min(w/vw,h/vh))])
            ramp=min(.12,length/2)
            self.animate(overlay,'opacity','opacity',[(at,0),(at+ramp,100),(at+length-ramp,100),(at+length,0)])
        self.scene_clips.append({'number':scene['number'],'clip':clip,'source':str(Path(source).resolve()),'start':start,'end':start+duration})
        return clip

    def effect(self,e,start,duration):
        kind=e['type']
        if kind=='impact_shake':return
        w,h=self.size;at=start+e['start']*duration;length=(e['end']-e['start'])*duration
        cx,cy=e['center'][0]*w,e['center'][1]*h;r=e['radius']*min(w,h);strength=e['intensity']
        tint=color(e['color']);shapes=[]
        if kind in ('impact_flash','atmospheric_haze'):
            shapes=[(self.shape('rectangle',(w/2,h/2),(w,h),at,length,tint),43 if kind=='impact_flash' else 18)]
        elif kind in ('focus_glow','light_sweep'):
            # Concentric editable vector layers give a soft falloff without a pixel cache.
            for i in range(6):
                radius=r*(1-i*.12)
                c=self.shape('ellipse',(cx,cy),(radius*2,radius*2),at,length,tint)
                if kind=='light_sweep':self.animate(c,'graphic_shape','position',[(at,[w*.2,cy]),(at+length,[w*.8,cy])])
                shapes.append((c,5))
        elif kind=='shock_ring':
            c=self.shape('ellipse',(cx,cy),(r*2,r*1.3),at,length,tint,props={'fill':False,'stroke':True,'stroke_color':tint,'stroke_width':max(1,w*.004)})
            self.animate(c,'graphic_shape','scale',[(at,10),(at+length,110)]);shapes=[(c,86)]
        elif kind=='subtle_vignette':
            for pos,size,angle in [((w*.1,h/2),(w*.2,h),0),((w*.9,h/2),(w*.2,h),180),
                ((w/2,h*.1),(w,h*.2),90),((w/2,h*.9),(w,h*.2),270)]:
                c=self.shape('rectangle',pos,size,at,length,'#000000',props={'fill_kind':'Linear Gradient',
                    'gradient_start':'#000000ff','gradient_end':'#00000000','gradient_angle':angle})
                shapes.append((c,32))
        elif kind in ('particle_burst','warm_dust_motes','debris_burst'):
            for i in range(12 if kind=='debris_burst' else 22):
                angle=i*2.399963;dist=r*(.2+(i%5)*.15);size=max(2,w*(.014 if kind=='debris_burst' else .005))
                x=cx+math.cos(angle)*dist;y=cy+math.sin(angle)*dist
                c=self.shape('polygon' if kind=='debris_burst' else 'ellipse',(x,y),(size,size),at,length,tint)
                initial=[x,y] if kind=='warm_dust_motes' else [cx,cy]
                end=[x,y-h*.04] if kind=='warm_dust_motes' else [x,y]
                self.animate(c,'graphic_shape','position',[(at,initial),(at+length,end)])
                shapes.append((c,86 if kind=='debris_burst' else 70))
        elif kind in ('speedline_burst','energy_trail'):
            points=[(cx-r*.8,cy+r*.35),(cx-r*.16,cy-r*.42),(cx+r*.18,cy+r*.1),(cx+r*.9,cy-r*.32)]
            for i in range(24 if kind=='speedline_burst' else 3):
                if kind=='speedline_burst':
                    angle=i*math.pi/12;a=(cx+math.cos(angle)*r*.45,cy+math.sin(angle)*r*.45);b=(cx+math.cos(angle)*r*1.8,cy+math.sin(angle)*r*1.8)
                else:a,b=points[i:i+2]
                c=self.shape('rectangle',((a[0]+b[0])/2,(a[1]+b[1])/2),(math.dist(a,b),max(2,w*.002)),at,length,tint,
                    props={'rotation':math.degrees(math.atan2(b[1]-a[1],b[0]-a[0]))})
                shapes.append((c,51 if kind=='speedline_burst' else 86))
        else:raise ValueError('Unsupported native effect: '+kind)
        for c,opacity in shapes:
            self.animate(c,'graphic_shape','opacity',[(at,0),(at+length*.15,opacity*strength),(at+length*.7,opacity*strength),(at+length,0)])

    def audio_clip(self,path,start,duration,track,source_in=0,volume=1):
        clip,info=self.place(path,start,duration,track=track,source_in=source_in,audio=True)
        if not info.get('audio_streams'):raise ValueError('Native audio source has no audio stream')
        db=-287.5 if volume<=0 else 20*math.log10(volume)
        self.batch([self.param(clip,'volume','level',max(-287.5,min(12,db)))])
        return clip,info

    def captions(self,rows,settings):
        from services.subtitle_layout import subtitle_font_pixels,subtitle_outline_pixels
        from filmcraft_profile import caption_face,caption_metrics
        if not rows:return
        def setting(*keys,default=None):return next((settings[k] for k in keys if settings.get(k) is not None),default)
        family=str(setting('subtitle_font_family','fontFamily','subtitle_font','font',default='Malgun Gothic'))
        face=caption_face(family);family=face['family']
        self.inputs.append({'path':face['file'],'sha256':sha(face['file']),'role':'subtitle_font'})
        fonts=self.call('fonts.list',{'system':True})
        if not any(f['family'].casefold()==family.casefold() for f in fonts):raise ValueError('Install the selected subtitle font for native FilmCraft: '+family)
        validate_caption_glyphs(family,rows)
        w,h=self.size
        raw=str(setting('subtitle_pos_y','posY','pos_y',default='b:12%'));match=re.search(r'-?\d+(?:\.\d+)?',raw);value=float(match.group()) if match else 12
        margin=value/100 if raw.startswith('b:') or '%' in raw or abs(value)<=100 else value/h
        if not 0<=margin<=.45:raise ValueError('Native caption bottom margin must be within 0..45%')
        if float(setting('subtitle_bg_v_offset','bgVOffset','bg_v_offset',default=0)):
            raise ValueError('Native captions require zero background-only vertical offset')
        enabled=setting('subtitle_bg_enabled','bgEnabled','bg_enabled',default=False) in (True,1,'1','true')
        opacity=float(setting('subtitle_bg_opacity','bgOpacity','bg_opacity',default=.5))
        if opacity>1:opacity/=100
        self.call('captions.newTrack',{'format':'Subtitle','name':'AIR finalized subtitles'})
        spacing=1+float(setting('subtitle_line_spacing','lineSpacing','line_spacing_ratio','line_spacing',default=.1))
        pixels=subtitle_font_pixels(setting('subtitle_font_size','fontSize','font_size',default=5),w)
        native_size,margin_offset=caption_metrics(face,pixels,spacing,h)
        style={'track':'C1','font':family,'size':native_size,
            'color':color(setting('subtitle_text_color','textColor','subtitle_base_color','font_color',default='#ffffff')),
            'outline':subtitle_outline_pixels(setting('subtitle_stroke_width','strokeWidth','stroke_width',default=2),w)*1080/h,
            'outlineColor':color(setting('subtitle_stroke_color','strokeColor','stroke_color',default='#000000')),
            'background':enabled,'backgroundColor':color(setting('subtitle_bg_color','bgColor','bg_color',default='#000000'),opacity),
            'align':'center','anchor':'bottom','margin':max(0,min(.45,margin+margin_offset)),
            'lineSpacing':spacing}
        if not 4<=style['size']<=400 or not .8<=style['lineSpacing']<=4:raise ValueError('Caption style exceeds native FilmCraft bounds')
        self.call('captions.setStyle',style)
        self.batch(caption_commands(rows,self.fps))

    def soundtrack(self,voice,settings,cues,voice_start=0):
        self.audio_clip(voice,0,self.duration,'A1',source_in=voice_start)
        bgm=settings.get('bgm_path')
        if bgm:
            from services.bgm_timeline import bgm_window
            start,end,fade_in,fade_out=bgm_window(settings,self.duration)
            _,info=self.import_media(bgm);available=info['duration']/TICKS
            if available<=0:raise ValueError('BGM source has no duration')
            position=start;volume=max(0,min(1,float(settings.get('bgm_volume',.08))))
            while position<end-1/self.fps:
                length=min(available,end-position);self.audio_clip(bgm,position,length,'A2',volume=volume);position+=length
                if not settings.get('bgm_loop',True):break
            fade_keys={start:0 if fade_in else 1,end:0 if fade_out else 1}
            for i in range(1,17):
                if fade_in:fade_keys[start+fade_in*i/16]=i/16
                if fade_out:fade_keys[end-fade_out+fade_out*(i-1)/16]=1-(i-1)/16
            self.batch([('mixer.setKeyframe',{'strip':'A2','lane':'volume','time':ticks(t),
                'value':max(-96,20*math.log10(max(v,1e-14)))}) for t,v in sorted(fade_keys.items())])
        for cue in sorted(cues,key=lambda c:float(c.get('start',c.get('time',0)))):
            if cue.get('enabled') is False:continue
            start=max(0,float(cue.get('start',cue.get('time',0))))
            if start>=self.duration:continue
            _,info=self.import_media(cue['path']);length=min(self.duration-start,info['duration']/TICKS,
                max(.2,min(30,float(cue['duration']))) if cue.get('duration') else self.duration)
            if length<=0:raise ValueError('SFX source has no duration')
            index=next((i for i,end in enumerate(self.sfx_ends) if end<=start),len(self.sfx_ends))
            if index>=126:raise ValueError('Too many simultaneous native sound cues')
            if index==len(self.sfx_ends):self.sfx_ends.append(start+length)
            else:self.sfx_ends[index]=start+length
            self.audio_clip(cue['path'],start,length,'A'+str(index+3),volume=10**(max(-60,min(12,float(cue.get('volume_db',-18))))/20))

    def export(self,gpu_mode='auto',export_settings=None):
        for asset in self.inputs:
            if sha(asset['path'])!=asset['sha256']:raise ValueError('Native source changed before export')
        inspected=self.run(['--project',self.project,'inspect'],'inspect')
        (self.directory/'native-timeline.json').write_text(json.dumps(inspected,ensure_ascii=False,indent=2),encoding='utf-8')
        from filmcraft_profile import encoding_profile
        encoding=encoding_profile(CONTRACT,self.size,self.fps)
        if export_settings:encoding.update(export_settings)
        result=self.run(['--project',self.project,'export',self.output,'--format','h264','--range','entire',
            '--gpu-rendering',gpu_mode,'--settings',json.dumps(encoding)],'export')
        gpu=result.get('gpuComposition')
        if not isinstance(gpu,dict):raise ValueError('Native GPU composition receipt missing')
        if gpu_mode=='auto' and gpu.get('compositedFrames',0)<=0:raise ValueError('Native GPU compositor did not render any frames; CPU-only output is not approved')
        if gpu_mode=='auto' and (gpu.get('adapter') or {}).get('deviceType') not in ('DiscreteGpu','IntegratedGpu','VirtualGpu'):
            raise ValueError('A hardware GPU adapter is required; software/unknown adapters are not approved')
        if not self.output.is_file() or not self.output.stat().st_size or result.get('offlineMedia'):raise ValueError('Incomplete native export')
        for asset in self.inputs:
            if sha(asset['path'])!=asset['sha256']:raise ValueError('Native source changed during export')
        receipt={'engine':'filmcraft','revision':PIN['revision'],'adapter':VERSION,'native_timeline':True,
            'profile':CONTRACT['profile'],'encoding':encoding,
            'gpu_mode':gpu_mode,'gpu_composition':gpu,'inputs':self.inputs,'scene_clips':self.scene_clips,
            'project':str(self.project),'project_sha256':sha(self.project),'output_sha256':sha(self.output),
            'export':result,'review_status':'rendered_requires_actual_review'}
        (self.directory/'filmcraft-receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2),encoding='utf-8')
        self.fresh();return self.output


def render_scene(snapshot,scene,plan,source,directory,fresh,voice=None,ai_source=None):
    motion=plan['scene'];validate_scene(snapshot,scene,motion)
    duration=scene['end']-scene['start'];size=(1080,1920) if snapshot['motion']['aspect']=='9:16' else (1920,1080)
    timeline=NativeTimeline(directory,snapshot['motion']['fps'],size,duration,fresh)
    if scene.get('direction_contract')=='scene_direction_plan/v2' and motion['transition']=='crossfade':motion={**motion,'transition':'cut'}
    timeline.source_scene({**scene,'_native_ai_plan':plan.get('ai')},motion,source,0,ai_source=ai_source)
    if voice:timeline.soundtrack(voice,{},[],voice_start=scene['start'])
    return timeline.export()


def preflight_gpu(directory,fresh,fps=24):
    """Verify a hardware composition submission before direction work or paid AI inserts."""
    timeline=NativeTimeline(directory,fps,(16,16),1/fps,fresh)
    timeline.export()
    return json.loads((timeline.directory/'filmcraft-receipt.json').read_text(encoding='utf-8'))['gpu_composition']


def render_master(snapshot,*,sources,plans,voice,directory,fresh,settings=None,sfx_cues=None,template_overlay_path=None,ai_sources=None,export_settings=None):
    size=(1080,1920) if snapshot['motion']['aspect']=='9:16' else (1920,1080)
    duration=snapshot['scenes'][-1]['end'];timeline=NativeTimeline(directory,snapshot['motion']['fps'],size,duration,fresh)
    for scene in snapshot['scenes']:
        plan=next(p for p in plans if p['number']==scene['number']);motion=plan['scene'];validate_scene(snapshot,scene,motion)
        if plan.get('ai') and not (ai_sources or {}).get(scene['number']):raise ValueError('Reviewed AI source missing from native master')
        timeline.source_scene({**scene,'_native_ai_plan':plan.get('ai')},motion,sources[scene['number']],scene['start'],
            ai_source=(ai_sources or {}).get(scene['number']))
    settings=settings if settings is not None else snapshot['settings']
    if template_overlay_path:
        clip,info=timeline.place(template_overlay_path,0,duration,track='V128')
        w,h=info['video']['width'],info['video']['height']
        timeline.batch([timeline.param(clip,'motion','uniform_scale',False),timeline.param(clip,'motion','scale',size[1]/h*100),
            timeline.param(clip,'motion','scale_width',size[0]/w*100)])
    timeline.captions(snapshot.get('subtitles',[]),settings)
    timeline.soundtrack(voice,settings,sfx_cues or [])
    return timeline.export(export_settings=export_settings)
