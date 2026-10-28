"""Measure ONLY final assembly of the same completed AE/EffectCraft scene clips.

No direction/AE/EffectCraft rendering, no cloud IO, no production changes.
"""
import json,math,os,re,statistics,subprocess,sys,time,wave
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'worker'))
from scripts.filmcraft import sha


def main():
    import worker_config  # Same environment as the active local final worker.
    from ae_media_utils import ffmpeg
    from services.ffmpeg_slideshow_service import render_ffmpeg_slideshow
    from services.filmcraft_final_service import render_final
    from motion_automation_worker import pcm
    from moviepy import VideoFileClip
    from PIL import Image,ImageDraw
    import numpy as np
    base=ROOT/'output/effectcraft/psd-3376-scene25-motion-fix-20261021'
    directory=ROOT/'output/filmcraft/completed-scene-final-comparison';directory.mkdir(parents=True,exist_ok=True)
    source_voice=ROOT/'output/motion-final-production/scene-25-recording.wav'
    voice=directory/'finalized-scene25-voice.wav'
    subprocess.run([ffmpeg(),'-v','error','-y','-i',str(source_voice),'-ar','48000','-ac','1','-c:a','pcm_s16le',str(voice)],check=True)
    with wave.open(str(voice),'rb') as audio:duration=audio.getnframes()/audio.getframerate()
    frozen=json.loads((ROOT/'output/motion-final-production/frozen-recording.json').read_text(encoding='utf8'))
    rows=[r for r in frozen['project']['project_payload']['subtitles'] if r.get('scene_number')==25]
    start=min(r['start'] for r in rows)
    subtitles=[{'text':r['text'],'start':r['start']-start,'end':min(duration,r['end']-start)} for r in rows if r['start']-start<duration]
    settings={'subtitle_font_family':'Noto Sans KR','subtitle_font_size':5.4,'subtitle_pos_y':'b:5%',
        'subtitle_stroke_width':0,'subtitle_text_color':'#ffffff','subtitle_bg_enabled':False,
        'subtitle_line_spacing':.1,'bg_color':'#000000'}
    use_gpu=os.getenv('USE_GPU_RENDER','true').lower()=='true'
    sources={'AE':base/'ae-reference.mp4','EffectCraft':base/'effectcraft.mp4'}
    inputs={'topic':3376,'scene':25,'duration':duration,'resolution':[1920,1080],'fps':24,
        'sources':{k:{'path':str(v),'sha256':sha(v),'effect_video_duration':10} for k,v in sources.items()},
        'voice':str(voice),'voice_sha256':sha(voice),'original_voice_sha256':sha(source_voice),
        'subtitles':subtitles,'settings':settings,'bgm':None,'sfx':[],'legacy_use_gpu':use_gpu,
        'timing':'Both retime the same completed 10s effect clip to the finalized recorded scene duration. Voice timing unchanged.',
        'scope':'Final assembly only. Inputs prepared once outside timing. No scene effect generation. Setup/font/timeline/mix/encode/copy inside each final renderer are timed.'}
    (directory/'inputs.json').write_text(json.dumps(inputs,ensure_ascii=False,indent=2),encoding='utf8')
    timing_path=directory/'timings.json';results=json.loads(timing_path.read_text()) if timing_path.exists() else []
    for effect_engine,source in sources.items():
        for run in (1,2,3):
            order=('python','filmcraft') if run%2 else ('filmcraft','python')
            for final_engine in order:
                if any(r['effect_engine']==effect_engine and r['final_engine']==final_engine and r['run']==run for r in results):continue
                work=directory/effect_engine/f'{final_engine}-{run}'
                if work.exists():work.rename(work.with_name(work.name+'-interrupted-'+str(time.time_ns())))
                work.mkdir(parents=True)
                print(f'{effect_engine} completed clip -> {final_engine} final: run {run}',flush=True)
                began=time.perf_counter()
                common=dict(temp_dir=str(work),images=[str(source)],durations=[duration],audio_path=str(voice),
                    subtitles=subtitles,resolution=(1920,1080),image_effects=['none'],transition_effects=['none'],
                    sfx_cues=[],progress_callback=lambda *_:None)
                if final_engine=='python':
                    output=Path(render_ffmpeg_slideshow(**common,subtitle_settings=settings,use_gpu=use_gpu))
                else:
                    output=render_final(**common,settings=settings,scene_numbers=[25])
                seconds=time.perf_counter()-began
                assert sha(source)==inputs['sources'][effect_engine]['sha256']
                result={'effect_engine':effect_engine,'final_engine':final_engine,'run':run,'seconds':seconds,
                    'output':str(output),'bytes':output.stat().st_size,'sha256':sha(output)}
                if final_engine=='filmcraft':
                    receipt=json.loads((work/'filmcraft-final/filmcraft-receipt.json').read_text(encoding='utf8'))
                    result.update(gpu=receipt['gpu_composition'],encoding=receipt['encoding'],native_export=receipt['export']['result'])
                else:
                    log=(work/'ffmpeg.fast.log').read_text(encoding='utf8',errors='replace')
                    result['encoder_log']=[s.strip() for s in log.splitlines() if 'encoder' in s.lower() or 'nvenc' in s.lower()]
                results.append(result);timing_path.write_text(json.dumps(results,indent=2),encoding='utf8')
                print(f'  {seconds:.3f}s, {output.stat().st_size/1e6:.3f}MB',flush=True)
    report={'inputs':inputs,'runs':results,'cases':{},'deployment':False}
    def metrics(encoded,reference,logname):
        # Same RGB picture ROI and SAME completed source reference for both outputs.
        command=[ffmpeg(),'-hide_banner','-i',str(encoded),'-i',str(reference),
            '-filter_complex','[0:v]crop=1920:900:0:0[a];[1:v]crop=1920:900:0:0[b];[a][b]ssim','-f','null','-']
        r=subprocess.run(command,capture_output=True,text=True,errors='replace',check=True)
        logname.write_text(r.stderr,encoding='utf8');ssim=float(re.findall(r'All:([\d.]+)',r.stderr)[-1])
        command[command.index('-filter_complex')+1]=command[command.index('-filter_complex')+1].replace('ssim','psnr')
        r=subprocess.run(command,capture_output=True,text=True,errors='replace',check=True)
        return {'ssim':ssim,'psnr_db':float(re.findall(r'average:([\d.]+)',r.stderr)[-1])}
    for effect_engine,source in sources.items():
        case_dir=directory/effect_engine;qa=case_dir/'quality';qa.mkdir(exist_ok=True)
        outputs={e:Path(next(r['output'] for r in results if r['effect_engine']==effect_engine and r['final_engine']==e and r['run']==3)) for e in ('python','filmcraft')}
        # Reference uses the legacy timing policy (segment tail .001s); no video encoder.
        sample_indices=[12,60,120,180,240,288]
        times=[i/24 for i in sample_indices if i/24<duration-.05]
        with VideoFileClip(str(source),audio=False) as video:
            for index,t in enumerate(times):
                Image.fromarray(video.get_frame(t*10/(duration+.001))).save(qa/f'source-{index:02}.png')
        frames={};inspection={};reference_audio=pcm(voice)
        for final_engine,path in outputs.items():
            with VideoFileClip(str(path)) as video:
                frames[final_engine]=[video.get_frame(t) for t in times]
                assert all(float(frame[:900].mean())>5 for frame in frames[final_engine]),'Unexpected black picture'
                count=sum(1 for _ in video.iter_frames())
                assert video.size==[1920,1080] and video.fps==24 and abs(video.duration-duration)<.1
                assert abs(count-math.ceil(duration*24))<=1
                inspection[final_engine]={'duration':video.duration,'frames':count,'fps':video.fps}
                for index,frame in enumerate(frames[final_engine]):Image.fromarray(frame).save(qa/f'{final_engine}-{index:02}.png')
            samples=pcm(path);n=min(len(samples),len(reference_audio));correlation=float(np.corrcoef(reference_audio[:n],samples[:n])[0,1])
            assert correlation>.99
            inspection[final_engine].update(voice_correlation=correlation,audio_rms=float(np.sqrt(np.mean(samples**2))))
            inspection[final_engine]['quality']=metrics(qa/f'{final_engine}-%02d.png',qa/'source-%02d.png',qa/f'{final_engine}-ssim.log')
        audio_a=pcm(outputs['python']);audio_b=pcm(outputs['filmcraft']);n=min(len(audio_a),len(audio_b))
        pair_correlation=float(np.corrcoef(audio_a[:n],audio_b[:n])[0,1]);assert pair_correlation>.99
        means={e:statistics.mean(r['seconds'] for r in results if r['effect_engine']==effect_engine and r['final_engine']==e) for e in outputs}
        medians={e:statistics.median(r['seconds'] for r in results if r['effect_engine']==effect_engine and r['final_engine']==e) for e in outputs}
        sheet=Image.new('RGB',(1280,3*385),'#161a20')
        for row,index in enumerate((0,len(times)//2,len(times)-1)):
            for column,e in enumerate(('python','filmcraft')):
                sheet.paste(Image.fromarray(frames[e][index]).resize((640,360)),(column*640,row*385+25))
                ImageDraw.Draw(sheet).text((column*640+8,row*385+5),f'{effect_engine} effects -> {e} final | {times[index]:.2f}s',fill='white')
        sheet.save(case_dir/'comparison.png')
        side=case_dir/'side-by-side.mp4'
        subprocess.run([ffmpeg(),'-v','error','-y','-i',str(outputs['python']),'-i',str(outputs['filmcraft']),
            '-filter_complex','[0:v]scale=960:540[a];[1:v]scale=960:540[b];[a][b]hstack=inputs=2[v]',
            '-map','[v]','-map','0:a:0','-c:v','libx264','-preset','veryfast','-crf','18','-c:a','copy','-movflags','+faststart',str(side)],check=True)
        report['cases'][effect_engine]={'mean_seconds':means,'median_seconds':medians,'inspection':inspection,
            'python_over_filmcraft_time_ratio':means['python']/means['filmcraft'],
            'bytes':{e:p.stat().st_size for e,p in outputs.items()},'outputs':{e:str(p) for e,p in outputs.items()},
            'audio_pair_correlation':pair_correlation,'comparison_video':str(side)}
    (directory/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8')
    print(json.dumps(report['cases'],ensure_ascii=True),flush=True)


if __name__=='__main__':main()
