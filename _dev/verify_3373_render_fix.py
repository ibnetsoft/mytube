import sys,json,subprocess,concurrent.futures,threading
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT),str(ROOT/'worker')]
from dotenv import load_dotenv
for f in ['.env','.env.local','auth-web/.env.local']:load_dotenv(ROOT/f)
from worker.lipsync_video_worker import ffmpeg
from services.ffmpeg_slideshow_service import render_ffmpeg_slideshow
from services.remote_render_service import _probe_media_duration
out=ROOT/'_dev/artifacts/final_3373_current_v4';c=json.loads((out/'config.json').read_text(encoding='utf8'))
starts=c['image_timing_starts'];total=c['audio_duration'];durations=[(starts[i+1] if i<100 else total)-starts[i] for i in range(101)]
lock=threading.Lock();finished=[]
def render(index):
 first=index*10;last=min(first+10,101);start=starts[first];end=starts[last] if last<101 else total
 directory=out/f'regression-chunk-{index:02}';directory.mkdir(exist_ok=True);audio=directory/'narration.wav'
 subprocess.run([ffmpeg(),'-y','-i',str(out/'narration.mp3'),'-ss',str(start),'-t',str(end-start),'-c:a','pcm_s16le',str(audio)],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
 subs=[{**s,'start':max(0,float(s['start'])-start),'end':min(end-start,float(s['end'])-start)} for s in c['subtitles'] if float(s['end'])>start and float(s['start'])<end]
 settings={**c['render_settings'],'timing_locked_indices':[i-first for i in c['render_settings']['timing_locked_indices'] if first<=i<last]}
 overlay=ROOT/'_dev/artifacts/final_3373_ae_v3/overlays/std_template_overlay.png'
 def progress(p,m):(directory/'progress.txt').write_text(json.dumps({'progress':p,'message':m},ensure_ascii=False),encoding='utf8')
 result=render_ffmpeg_slideshow(temp_dir=str(directory),images=[str(out/'images'/p) for p in c['images'][first:last]],audio_path=str(audio),durations=durations[first:last],subtitles=subs,subtitle_settings=settings,image_effects=['none']*(last-first),transition_effects=['none']*(last-first),resolution=(1920,1080),template_overlay_path=str(overlay) if overlay.exists() else None,use_gpu=True,progress_callback=progress,sfx_cues=[])
 actual=_probe_media_duration(ffmpeg(),result);assert abs(actual-(end-start))<.15,(index,actual,end-start)
 with lock:
  finished.append(index);(out/'progress.txt').write_text(json.dumps({'progress':round(len(finished)/11*90),'message':f'분할 렌더 {len(finished)}/11 완료'},ensure_ascii=False),encoding='utf8');print('CHUNK_DONE',index,len(finished),flush=True)
 return result

render(2)
