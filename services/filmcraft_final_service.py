"""Final assembly only. AE/EffectCraft scene outputs are immutable input clips."""
from pathlib import Path
import json,math,shutil,sys

ROOT=Path(__file__).resolve().parents[1]
if str(ROOT/'worker') not in sys.path:sys.path.insert(0,str(ROOT/'worker'))


def render_final(*,temp_dir,images,durations,audio_path,subtitles,settings,resolution,
                 scene_numbers=None,sfx_cues=None,template_overlay_path=None,
                 image_effects=None,transition_effects=None,intro_video_path=None,
                 progress_callback=None,fresh=lambda:None):
    from filmcraft_native import NativeTimeline,color
    from filmcraft_render import CONTRACT
    if len(images)!=len(durations) or not images:raise ValueError('FilmCraft final scene timeline is incomplete')
    if intro_video_path:raise ValueError('FilmCraft final intro must be included as a timed scene')
    comic=settings.get('comic') or {}
    if comic.get('mode') in ('comic','moving_comic'):raise ValueError('Comic page layouts must be prepared as visual clips before FilmCraft final assembly')
    progress=progress_callback or (lambda *_:None)
    fps=(settings.get('motion') or {}).get('fps',24)
    if fps not in (24,30):raise ValueError('FilmCraft final supports 24 or 30 fps')
    if any(not math.isfinite(float(d)) or float(d)<=0 for d in durations):raise ValueError('Invalid FilmCraft final duration')
    directory=Path(temp_dir)/'filmcraft-final';timeline=NativeTimeline(directory,fps,resolution,sum(durations),fresh)
    # V1 holds the background; completed scene clips go on V2. A V2 background
    # leaves a tail item that prevents a retimed clip from extending past its
    # original end when Speed/Duration is applied without ripple.
    timeline.call('graphics.set',{'clip':timeline.background_clip,'props':{'fill_color':color(settings.get('bg_color','#000000'))}})
    progress(35,'FilmCraft 최종 합성 · 효과 완료 씬 배치')
    position=0
    for index,(path,duration) in enumerate(zip(images,durations)):
        _,probe=timeline.import_media(path)
        is_video=str(probe['kind']).lower() in ('movie','video')
        effect='none' if is_video else str((image_effects or ['none']*len(images))[index] or 'none').lower()
        keys=[]
        for step in range(17):
            t=step/16;u=(1-math.cos(math.pi*t))/2;x=y=.5;scale=1.
            if effect in ('none','static'):pass
            elif effect in ('auto_classify','zoom_in','zoom_out'):
                scale=1+.08*(1-u if effect=='zoom_out' else u)
            elif effect in ('pan_left','pan_right','pan_up','pan_down','scroll_up','scroll_down'):
                scale=1.12;offset=(u-.5)*.12
                if effect in ('pan_left','pan_right'):x+=offset*(1 if effect=='pan_left' else -1)
                else:y+=offset*(1 if effect in ('pan_up','scroll_up') else -1)
            else:raise ValueError('Unsupported FilmCraft final image motion: '+effect)
            keys.append(dict(t=t,x=x,y=y,scale=scale,rotation=0,opacity=100))
        transition=str((transition_effects or ['none']*len(images))[index] or '').lower()
        if transition not in ('','none','cut','fade','crossfade','dissolve'):raise ValueError('Unsupported FilmCraft final transition: '+transition)
        plan={'source':'video' if is_video else 'image','fit':'cover','direction':'Final assembly of completed scene; no AE/EffectCraft effects are re-applied',
            'keys':keys,'effects':[],'transition':'crossfade' if index and transition not in ('none','cut') else 'cut','transition_seconds':.5}
        number=(scene_numbers or list(range(1,len(images)+1)))[index]
        authored=(settings.get('motion') or {}).get('scenes',{}).get(str(number))
        if authored and not is_video:
            if any(authored.get(k) for k in ('layers','native','finance','cues')):raise ValueError('Prepare layered/browser effects as clips before final assembly')
            plan=authored
        available=float(probe.get('duration',0))/254016000000 if is_video else duration
        if is_video and available>0 and available+1/fps<duration:
            if duration/available<=3:
                clip=timeline.source_scene({'number':number,'source_kind':'video','start':position,'end':position+available},plan,path,position)
                timeline.call('clip.speedDuration',{'clips':[clip],'speed':100*available/duration,'ripple':False,'interpolation':'frameSampling'})
                timeline.scene_clips[-1]['end']=position+duration
            else:
                offset=0
                while offset<duration-1e-8:
                    length=min(available,duration-offset)
                    timeline.source_scene({'number':number,'source_kind':'video','start':position+offset,'end':position+offset+length},
                        {**plan,'transition':plan['transition'] if offset==0 else 'cut'},path,position+offset)
                    offset+=length
        else:
            timeline.source_scene({'number':number,'source_kind':plan['source'],'start':position,'end':position+duration},plan,path,position)
        position+=duration
    if template_overlay_path:
        clip,info=timeline.place(template_overlay_path,0,position,track='V128')
        w,h=info['video']['width'],info['video']['height']
        timeline.batch([timeline.param(clip,'motion','uniform_scale',False),timeline.param(clip,'motion','scale',resolution[1]/h*100),timeline.param(clip,'motion','scale_width',resolution[0]/w*100)])
    timeline.captions(subtitles,settings);timeline.soundtrack(audio_path,settings,sfx_cues or [])
    progress(50,'FilmCraft GPU 최종 렌더 · 자막·음성·BGM·효과음')
    output=timeline.export()
    target=Path(temp_dir)/'output.mp4';shutil.copy2(output,target)
    (Path(temp_dir)/'final-renderer.json').write_text(json.dumps({'engine':'filmcraft','profile':CONTRACT['profile'],
        'receipt':str(directory/'filmcraft-receipt.json'),'effect_engine_unchanged':True}),encoding='utf8')
    progress(100,'FilmCraft 최종 렌더 완료')
    return target
