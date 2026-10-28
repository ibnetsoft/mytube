"""Re-run the existing project scene with matched size and calibrated native captions."""
import json,math,re,statistics,subprocess,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'worker'))
from scripts.calibrate_filmcraft_legacy import D,OLD
from scripts.filmcraft import sha


def main():
    from services.motion_render_service import render_motion,MotionFrames
    from filmcraft_native import render_master,NativeTimeline
    from filmcraft_render import binary,execute
    from motion_automation_worker import pcm
    from ae_media_utils import ffmpeg
    from moviepy import VideoFileClip
    from PIL import Image,ImageDraw
    import numpy as np
    info=json.loads((OLD/'inputs.json').read_text(encoding='utf8'))
    config=json.loads((D/'hardware-trial.json').read_text(encoding='utf8'))
    cal=json.loads((D/'caption-calibration.json').read_text())
    source=Path(info['source']);voice=OLD/'original-voice-window.wav'
    assert sha(source)==info['source_sha256'] and sha(voice)==info['voice_sha256']
    assert Path(cal['installed_font']).is_file()
    encoding=config['encoding'];settings=config['settings'];snapshot=config['snapshot']
    runfile=D/'matched-timings.json';results=json.loads(runfile.read_text()) if runfile.exists() else []
    for run,order in enumerate((('legacy','filmcraft'),('filmcraft','legacy')),1):
        for engine in order:
            if any(r['engine']==engine and r['run']==run for r in results):continue
            work=D/f'matched-{engine}-{run}'
            if work.exists():work.rename(D/f'matched-{engine}-{run}-failed-{time.time_ns()}')
            work.mkdir()
            print(f'Matched benchmark: {engine} run {run}',flush=True)
            begin=time.perf_counter()
            if engine=='legacy':
                output=Path(render_motion(temp_dir=str(work),images=[str(source)],durations=[info['duration']],
                    audio_path=str(voice),subtitles=info['subtitles'],settings=info['settings'],resolution=(1920,1080),scene_numbers=[37]))
            else:
                output=render_master(snapshot,sources={37:source},plans=[{'number':37,'scene':info['shared_plan']}],
                    voice=voice,directory=work,fresh=lambda:None,settings=settings,export_settings=encoding)
            elapsed=time.perf_counter()-begin
            row={'engine':engine,'run':run,'total_seconds':elapsed,'output':str(output),'bytes':output.stat().st_size,'sha256':sha(output)}
            if engine=='filmcraft':
                receipt=json.loads((work/'filmcraft-receipt.json').read_text(encoding='utf8'))
                row.update(gpu=receipt['gpu_composition'],native_export=receipt['export']['result'])
            results.append(row);runfile.write_text(json.dumps(results,indent=2),encoding='utf8')
            print(f'{engine} run {run}: {elapsed:.3f}s / {row["bytes"]} bytes',flush=True)
    outputs={e:Path(next(r['output'] for r in results if r['engine']==e and r['run']==2)) for e in ('legacy','filmcraft')}
    inspection={};frames={};times=[.5,2.5,5,8,12,15.5]
    qa=D/'matched-quality';qa.mkdir(exist_ok=True)
    for engine,path in outputs.items():
        with VideoFileClip(str(path)) as video:
            count=sum(1 for _ in video.iter_frames())
            assert video.size==[1920,1080] and video.fps==24 and count==390
            frames[engine]=[video.get_frame(t) for t in times]
            inspection[engine]={'frames':count,'duration':video.duration,'fps':video.fps,'resolution':video.size}
            for index,frame in enumerate(frames[engine]):Image.fromarray(frame).save(qa/f'{engine}-{index:02}.png')
        a=pcm(voice);b=pcm(path);n=min(len(a),len(b));correlation=float(np.corrcoef(a[:n],b[:n])[0,1])
        assert correlation>.99;inspection[engine]['audio_correlation']=correlation
    size_ratio=outputs['filmcraft'].stat().st_size/outputs['legacy'].stat().st_size
    assert .98<size_ratio<1.02,size_ratio
    # Lossless references for codec quality. The common legacy reference also
    # exposes differences in camera sampling/color between the compositors.
    reference=MotionFrames([str(source)],[info['duration']],[],info['settings'],(1920,1080),'',scene_numbers=[37])
    for index,t in enumerate(times):Image.fromarray(reference.frame(t)).save(qa/f'common-{index:02}.png')
    reference.close()
    project=D/'matched-filmcraft-2/timeline.fcproj'
    cli=binary()
    for index,t in enumerate(times):execute(cli,['--project',project,'render','--seconds',str(t),'--out',qa/f'native-ref-{index:02}.png'],qa,f'native-ref-{index}')
    def ssim(encoded,reference):
        stats=qa/f'{encoded}-vs-{reference}.ssim.log'
        command=[ffmpeg(),'-hide_banner','-i',str(qa/f'{encoded}-%02d.png'),'-i',str(qa/f'{reference}-%02d.png'),
            '-filter_complex','[0:v]crop=1920:900:0:0[a];[1:v]crop=1920:900:0:0[b];[a][b]ssim','-f','null','-']
        result=subprocess.run(command,capture_output=True,text=True,errors='replace',check=True)
        stats.write_text(result.stderr,encoding='utf8')
        return float(re.findall(r'All:([\d.]+)',result.stderr)[-1])
    quality={'legacy_vs_own_lossless':ssim('legacy','common'),'filmcraft_vs_own_lossless':ssim('filmcraft','native-ref'),
        'filmcraft_vs_common_lossless':ssim('filmcraft','common'),
        'method':'Six same-time full-resolution RGB samples; top 1920x900 picture area, captions measured separately. SSIM per own lossless compositor reference measures codec damage; common reference also includes compositor differences.'}
    assert abs(quality['legacy_vs_own_lossless']-quality['filmcraft_vs_own_lossless'])<.01,quality
    # Query encoding counters in the SAME native export process, avoiding guesses
    # from the hardwareEncoding=auto preference. This profiling export is not timed.
    profile_script=qa/'profile.jsonl';profile_output=qa/'native-profile.mp4'
    profile_script.write_text('\n'.join(json.dumps(row) for row in [
        {'id':'file.exportMedia','params':{'path':str(profile_output),'format':'h264','range':'entire','wait':True,'gpuRendering':'auto','settings':{**encoding,'includeAudio':True,'burnCaptions':True}}},
        {'id':'perf.stats','params':{}}])+'\n',encoding='utf8')
    profile=execute(cli,['--project',project,'run',profile_script],qa,'hardware-profile')
    hardware=profile[-1]['result']['export']['hardware']
    assert hardware['frames']==390 and hardware['declined']==0,hardware
    sheet=Image.new('RGB',(1280,3*385),'#161a20');draw=ImageDraw.Draw(sheet)
    for row,index in enumerate((0,3,5)):
        for column,engine in enumerate(('legacy','filmcraft')):
            sheet.paste(Image.fromarray(frames[engine][index]).resize((640,360)),(column*640,row*385+25))
            draw.text((column*640+8,row*385+5),f'{engine} | {times[index]:.2f}s',fill='white')
    sheet.save(D/'matched-comparison.png')
    side=D/'matched-side-by-side.mp4'
    subprocess.run([ffmpeg(),'-v','error','-y','-i',str(outputs['legacy']),'-i',str(outputs['filmcraft']),
        '-filter_complex','[0:v]scale=960:540[a];[1:v]scale=960:540[b];[a][b]hstack=inputs=2[v]',
        '-map','[v]','-map','0:a:0','-c:v','libx264','-preset','veryfast','-crf','18','-c:a','copy','-movflags','+faststart',str(side)],check=True)
    means={e:statistics.mean(r['total_seconds'] for r in results if r['engine']==e) for e in outputs}
    report={'project':3376,'scene':37,'source_sha256':sha(source),'voice_sha256':sha(voice),'input_snapshot':str(OLD/'inputs.json'),
        'runs':results,'mean_seconds':means,'speed_ratio':means['legacy']/means['filmcraft'],'size_ratio':size_ratio,
        'quality':quality,'inspection':inspection,'hardware_encoding_verified':hardware,'caption_calibration':cal,
        'native_encoding':encoding,'native_settings':settings,'side_by_side':str(side),
        'notes':['Both 1920x1080/24fps/390 frames. Same original source, camera, finalized voice, six subtitles.',
          'Native composition and native hardware H264/AAC directly, no frame re-encoding or FFmpeg export stage.',
          'Caption physical bounds match using same static font outlines; rasterizer anti-aliasing remains different.',
          'Legacy retains previous production libx264 settings. Native uses matching 1540kbps video, 192kbps mono AAC.',
          'Two fresh runs each, alternating order. Times include composition/timeline, captions, audio, encoding; exclude setup/calibration/QA/profile.',
          'This scene only, no claims about PSD rigs or full project speed. Background services running; OS cache not flushed.'],
        'deployment':False}
    (D/'matched-report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8')
    print(json.dumps({'means':means,'ratio':report['speed_ratio'],'size_ratio':size_ratio,'quality':quality,'hardware':hardware}),flush=True)


if __name__=='__main__':main()
