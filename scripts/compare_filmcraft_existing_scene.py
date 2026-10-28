"""Offline, non-publishing comparison of the active image compositor and native FilmCraft."""
from __future__ import annotations
import json, math, shutil, statistics, subprocess, sys, time
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'worker'))
from scripts.filmcraft import sha


def main():
    import numpy as np
    from PIL import Image,ImageDraw
    from moviepy import VideoFileClip
    from ae_media_utils import ffmpeg
    from services.motion_render_service import render_motion
    from filmcraft_native import render_master
    from filmcraft_render import PIN,VERSION
    from motion_automation_worker import pcm
    directory=ROOT/'output/filmcraft/existing-scene-3376-037-comparison'
    directory.mkdir(parents=True,exist_ok=True)
    frozen=ROOT/'output/motion-final-production/frozen-recording.json'
    data=json.loads(frozen.read_text(encoding='utf8'));payload=data['project']['project_payload']
    number=37;fps=24
    original=Path('C:/Users/kimse/AppData/Local/AIRStudio/AIRWorker/temp/ae_highlight/3376-037-motion-4aabe81caedf41a6/input/scene.png')
    source=directory/'source.png';shutil.copy2(original,source)
    assert sha(source)=='b6a918cd3eb368fa2204b9b3244e665daa03b0b6945154370b87f026cf5d02e7'
    rows=[r for r in payload['subtitles'] if r.get('scene_number')==number]
    start=min(r['start'] for r in rows);end=max(r['end'] for r in rows)
    duration=math.ceil((end-start)*fps)/fps
    subtitles=[{'start':r['start']-start,'end':r['end']-start,'text':r['text']} for r in rows]
    original_voice=ROOT/'output/motion-final-production/final-narration.mp3'
    assert sha(original_voice)==data['audio']['metadata']['sha256'],'Frozen narration mismatch'
    voice=directory/'original-voice-window.wav'
    subprocess.run([ffmpeg(),'-v','error','-y','-ss',str(start),'-i',str(original_voice),'-af','apad',
        '-t',str(duration),'-ar','48000','-c:a','pcm_s16le',str(voice)],check=True)
    saved=data['scenes'][number-1]['metadata']['ae_motion_plan']
    camera=saved['motion']
    plan={'source':'image','fit':'contain','direction':saved['direction'],
        'keys':[dict(t=0,x=.5,y=.5,scale=1,rotation=0,opacity=100),
                dict(t=1,x=.5+camera['drift_x'],y=.5+camera['drift_y'],scale=1+camera['push'],rotation=0,opacity=100)],
        'effects':[],'transition':'cut'}
    motion={'version':1,'enabled':True,'fps':fps,'aspect':'16:9','scenes':{str(number):plan}}
    settings={'motion':motion,'bg_color':'#0c1018','subtitle_font_family':'Noto Sans KR',
        'subtitle_font_size':5.4,'subtitle_pos_y':'b:5%','subtitle_bg_enabled':False,
        'subtitle_bg_v_offset':0,'subtitle_text_color':'#ffffff','subtitle_stroke_width':0,
        'subtitle_line_spacing':.1,'use_gpu':True}
    snapshot={'renderer':{'engine':'filmcraft','revision':PIN['revision'],'adapter':VERSION},
        'project':{'id':data['project']['id']},'motion':motion,'settings':settings,
        'scenes':[{'number':number,'source_kind':'image','start':0,'end':duration}], 'subtitles':subtitles}
    inputs={'project_id':data['project']['id'],'topic':3376,'scene':number,
        'source':str(source),'source_sha256':sha(source),'frozen_snapshot_sha256':sha(frozen),
        'voice_original_sha256':sha(original_voice),'voice_sha256':sha(voice),
        'recorded_window':[start,end],'duration':duration,'fps':fps,'resolution':[1920,1080],
        'saved_direction':saved,'shared_plan':plan,'settings':settings,'subtitles':subtitles,
        'notes':['Saved camera push/drift normalized into identical two-key execution for both engines.',
          'Full recorded scene retained; final frame padded to the next 24fps boundary.',
          'Both use Noto Sans KR instead of saved GmarketSansBold for verified Japanese glyph coverage.',
          'No BGM, SFX, AI, PSD, network, database or production queue changes.',
          'Each engine keeps production encoding defaults; this is pipeline time, not an encoder-only comparison.',
          'Initial and repeat runs alternate order; neither uses rendered-output caches. OS caches not flushed.']}
    (directory/'inputs.json').write_text(json.dumps(inputs,ensure_ascii=False,indent=2),encoding='utf8')
    results=json.loads((directory/'timings.json').read_text(encoding='utf8')) if (directory/'timings.json').exists() else []
    # Alternate order to reduce a consistent first-run advantage.
    for run,order in enumerate((('legacy','filmcraft'),('filmcraft','legacy')),1):
        for engine in order:
            if any(r['engine']==engine and r['run']==run for r in results):continue
            work=directory/f'{engine}-{run}'
            if work.exists():work.rename(directory/f'{engine}-{run}-failed-{time.time_ns()}')
            work.mkdir()
            print(f'Rendering {engine} run {run}: {duration:.3f}s, 1080p/{fps}',flush=True)
            begin=time.perf_counter()
            if engine=='legacy':
                output=Path(render_motion(temp_dir=str(work),images=[str(source)],durations=[duration],
                    audio_path=str(voice),subtitles=subtitles,settings=settings,resolution=(1920,1080),scene_numbers=[number]))
            else:
                output=render_master(snapshot,sources={number:source},plans=[{'number':number,'scene':plan}],
                    voice=voice,directory=work,fresh=lambda:None,settings=settings)
            elapsed=time.perf_counter()-begin
            result={'engine':engine,'run':run,'total_seconds':elapsed,'output':str(output),
                'sha256':sha(output),'bytes':output.stat().st_size}
            if engine=='filmcraft':
                receipt=json.loads((work/'filmcraft-receipt.json').read_text(encoding='utf8'))
                result['gpu']=receipt['gpu_composition'];result['export']=receipt['export']
            results.append(result)
            (directory/'timings.json').write_text(json.dumps(results,indent=2),encoding='utf8')
            print(f'Completed {engine} run {run}: {elapsed:.3f}s',flush=True)
    outputs={e:Path(next(r['output'] for r in results if r['engine']==e and r['run']==2)) for e in ('legacy','filmcraft')}
    inspection={};frames={}
    reference=pcm(voice)
    for engine,path in outputs.items():
        with VideoFileClip(str(path)) as video:
            count=sum(1 for _ in video.iter_frames())
            assert video.size==[1920,1080] and abs(video.fps-fps)<.01
            assert abs(video.duration-duration)<=1/fps+.01 and count>=round(duration*fps)-1
            frames[engine]=[video.get_frame(t) for t in (.5,duration/2,duration-.5)]
            info={'duration':video.duration,'fps':video.fps,'frames':count,'resolution':video.size}
        audio=pcm(path);n=min(len(audio),len(reference));corr=float(np.corrcoef(reference[:n],audio[:n])[0,1])
        assert corr>.97,(engine,corr)
        info.update(audio_correlation=corr,audio_rms=float(np.sqrt(np.mean(audio**2))))
        inspection[engine]=info
    sheet=Image.new('RGB',(1280,3*385),'#161a20');draw=ImageDraw.Draw(sheet)
    for i,t in enumerate((.5,duration/2,duration-.5)):
        for j,engine in enumerate(('legacy','filmcraft')):
            sheet.paste(Image.fromarray(frames[engine][i]).resize((640,360)),(j*640,i*385+25))
            draw.text((j*640+8,i*385+5),f'{engine} | {t:.2f}s',fill='white')
    sheet.save(directory/'comparison.png')
    side=directory/'side-by-side.mp4'
    subprocess.run([ffmpeg(),'-v','error','-y','-i',str(outputs['legacy']),'-i',str(outputs['filmcraft']),
        '-filter_complex','[0:v]scale=960:540[a];[1:v]scale=960:540[b];[a][b]hstack=inputs=2[v]',
        '-map','[v]','-map','0:a:0','-c:v','libx264','-preset','veryfast','-crf','18',
        '-c:a','copy','-movflags','+faststart',str(side)],check=True)
    means={e:statistics.mean(r['total_seconds'] for r in results if r['engine']==e) for e in outputs}
    report={'inputs':inputs,'runs':results,'mean_seconds':means,
        'legacy_over_filmcraft_ratio':means['legacy']/means['filmcraft'],'inspection':inspection,
        'sample_mae':[float(np.abs(a.astype(float)-b.astype(float)).mean()) for a,b in zip(frames['legacy'],frames['filmcraft'])],
        'side_by_side':str(side),'left':'legacy','right':'filmcraft','deployment':False}
    (directory/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8')
    lines=['# Project 3376, scene 37: existing renderer vs FilmCraft','',
        f'1920x1080, {fps}fps, {duration:.3f}s. Original image, finalized voice, same normalized camera keys and Japanese subtitles.',
        '', '| Renderer | First run | Repeat run | Mean |','|---|---:|---:|---:|']
    for e in outputs:
        times=[r['total_seconds'] for r in results if r['engine']==e]
        lines.append(f'| {e} | {times[0]:.3f}s | {times[1]:.3f}s | {means[e]:.3f}s |')
    lines+=['',f'Legacy / FilmCraft time ratio: {means["legacy"]/means["filmcraft"]:.3f}.',
        '', 'Times include timeline construction, composition, subtitles, audio and encoding; exclude asset staging, AI direction, queue/network, and QA.',
        'The legacy path is the current web worker image MotionFrames + production FFmpeg compositor, not a PSD/AE layer benchmark.',
        'FilmCraft uses native timeline + verified hardware GPU composition. Native export time is separately recorded in report.json.',
        'Each uses production encoding defaults; bitrate/codec implementation and caption rasterization differ.',
        'One camera-only image scene is not a general speed claim for effect-heavy videos or PSD rigs.',
        '',*inputs['notes'],'','side-by-side.mp4: LEFT legacy, RIGHT FilmCraft; shared narration from legacy output.',
        'No deployment or publishing performed.']
    (directory/'REPORT.md').write_text('\n'.join(lines)+'\n',encoding='utf8')
    print(json.dumps({'means':means,'ratio':report['legacy_over_filmcraft_ratio'],'directory':str(directory)}),flush=True)


if __name__=='__main__':main()
