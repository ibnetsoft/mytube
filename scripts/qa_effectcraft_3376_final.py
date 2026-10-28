"""Review actual assembled video, including every cut and the native delivery clips."""
import hashlib,json,math,re,shutil,subprocess,time
from pathlib import Path
import imageio_ffmpeg,numpy as np
from PIL import Image,ImageDraw,ImageOps
ROOT=Path(__file__).resolve().parents[1];D=ROOT/'output/effectcraft/project-3376-final-20261021';ff=imageio_ffmpeg.get_ffmpeg_exe()
read=lambda p:json.loads(Path(p).read_text(encoding='utf8'))
queue=read(D/'queue-current.json')
checkpoint=Path.home()/'AppData/Local/Temp/air-render-checkpoints'/queue['id'];video=checkpoint/'output.mp4';assert video.exists(),video
receipt=read(checkpoint/'encoder-completed.json')
assert receipt['bytes']==video.stat().st_size
assert queue['status']=='completed' or queue['status']=='rendering' and queue['progress']>=92
shutil.copy2(video,D/'effectcraft-3376-full.mp4');video=D/'effectcraft-3376-full.mp4'
r=read(D/'recording.json');rows=r['timings'];total=rows[-1]['end'];fps=24
# An actual full decode, with every scene midpoint and every cut sampled in a single pass.
indices=sorted({0,math.floor(total*fps)-1}|{min(math.floor(total*fps)-1,math.ceil((s['start']+s['end'])/2*fps)) for s in rows}|{max(0,math.ceil(s['start']*fps)+offset) for s in rows[1:] for offset in [-1,0,1,13]})
samples=D/'final-samples';samples.mkdir(exist_ok=True);expr='+'.join(f'eq(n,{n})' for n in indices)
cmd=[ff,'-v','error','-y','-i',str(video),'-map','0:v:0','-map','0:a:0','-f','null','NUL','-map','0:v:0','-vf',f"select='{expr}',scale=480:270",'-fps_mode','vfr','-q:v','2',str(samples/'sample-%04d.jpg'),'-progress','pipe:1']
p=subprocess.run(cmd,capture_output=True,text=True,encoding='utf8',errors='replace');(D/'decode-errors.txt').write_text(p.stderr,encoding='utf8');assert p.returncode==0 and not p.stderr.strip(),p.stderr
files=sorted(samples.glob('sample-*.jpg'));assert len(files)==len(indices),(len(files),len(indices))
sample_rows=[]
for i,(n,file) in enumerate(zip(indices,files)):
    image=np.array(Image.open(file));mean=float(image.mean());std=float(image.std());assert mean>3 and std>3,('Unexpected blank',n,mean,std)
    scene=next((s['number'] for s in rows if s['start']<=n/fps<s['end']),100);sample_rows.append(dict(frame=n,time=n/fps,scene=scene,file=str(file),mean=mean,std=std))
config=read(checkpoint/'config.json');original_images=[]
for index,shot in enumerate(rows):
    source=checkpoint/'images'/config['images'][index]
    if source.suffix.lower() not in ['.png','.jpg','.jpeg','.webp']:continue
    n=math.ceil((shot['start']+shot['end'])/2*fps);actual=next(s for s in sample_rows if s['frame']==n)
    with Image.open(source) as image:fit=ImageOps.contain(ImageOps.exif_transpose(image).convert('RGB'),(480,270),method=Image.Resampling.BICUBIC)
    expected=Image.new('RGB',(480,270),'#0c1018');expected.paste(fit,((480-fit.width)//2,(270-fit.height)//2))
    delta=np.array(Image.open(actual['file']).convert('RGB')).astype(float)[:189]-np.array(expected).astype(float)[:189]
    error=float(abs(delta).mean());assert error<6,('Original visual changed',shot['number'],error)
    original_images.append(dict(scene=shot['number'],mae_upper70=error,mean_rgb_bias=delta.mean(axis=(0,1)).tolist()))
# Compact, labelled contact sheets for direct inspection, separated into groups.
for page in range(math.ceil(len(files)/40)):
    subset=sample_rows[page*40:(page+1)*40];sheet=Image.new('RGB',(1920,10*294),'#111111');draw=ImageDraw.Draw(sheet)
    for j,s in enumerate(subset):
        x,y=(j%4)*480,(j//4)*294
        sheet.paste(Image.open(s['file']),(x,y+24));draw.text((x+5,y+4),f"scene {s['scene']} | {s['time']:.3f}s | frame {s['frame']}",fill='white')
    sheet.save(D/f'final-contact-{page:02}.jpg',quality=92)
def frame(v,t):
    return np.frombuffer(subprocess.check_output([ff,'-v','error','-ss',str(t),'-i',str(v),'-frames:v','1','-f','rawvideo','-pix_fmt','rgb24','-']),dtype=np.uint8).reshape(1080,1920,3).astype(float)
native=[]
for clip in read(D/'padded-clips.json'):
    shot=next(s for s in rows if s['number']==clip['number']);compares=[];times=[.75,1,2.5,4.5,7,shot['end']-shot['start']-.75]
    sheet=Image.new('RGB',(1440,len(times)*294),'#111111');draw=ImageDraw.Draw(sheet)
    for i,t in enumerate(times):
        # Compare on the same CFR timestamp used by the assembled timeline.
        n=math.ceil((shot['start']+t)*fps);actual_time=n/fps;local=actual_time-shot['start'];a=frame(video,actual_time);b=frame(clip['file'],math.floor(local*fps+.00001)/fps)
        # Captions are intentional; restrict metrics to the upper 70% of the frame.
        delta=a[:756]-b[:756];mae=float(abs(delta).mean());bias=delta.mean(axis=(0,1)).tolist();compares.append(dict(time=actual_time,local=local,mae_upper70=mae,mean_rgb_bias=bias))
        for col,img in enumerate([b,a,np.minimum(abs(a-b)*8,255)]):sheet.paste(Image.fromarray(img.astype('uint8')).resize((480,270)),(col*480,i*294+24))
        draw.text((5,i*294+4),f"Scene {clip['number']} {local:.3f}s: native delivery | final with captions | diff x8",fill='white')
    sheet.save(D/f'scene-{clip["number"]}-final-comparison.jpg',quality=92);native.append(dict(number=clip['number'],samples=compares))
    subprocess.run([ff,'-v','error','-y','-ss',str(max(0,shot['start']-1)),'-i',str(video),'-t',str(shot['end']-shot['start']+2),'-c:v','libx264','-preset','fast','-crf','18','-c:a','aac',str(D/f'scene-{clip["number"]}-with-boundaries.mp4')],check=True)
def audio(file):return np.frombuffer(subprocess.check_output([ff,'-v','error','-i',str(file),'-vn','-ac','1','-ar','8000','-f','f32le','-']),dtype='<f4')
voice=ROOT/'output/motion-final-production/final-narration.mp3';a,b=audio(voice),audio(video);length=min(len(a),len(b));corr=float(np.corrcoef(a[:length],b[:length])[0,1]);assert corr>.95,corr;assert abs(len(a)-len(b))/8000<.15
sha=hashlib.sha256(video.read_bytes()).hexdigest();result=dict(project_id=queue['metadata']['std_web_project_id'],queue_id=queue['id'],file=str(video),sha256=sha,full_decode=True,sample_count=len(indices),duration_seconds=total,audio_correlation=corr,audio_padding_seconds=(len(b)-len(a))/8000,original_image_comparisons=original_images,native_scene_comparisons=native,samples=sample_rows,review_status='awaiting_actual_contact_sheet_review')
(D/'final-qa.json').write_text(json.dumps(result,indent=2),encoding='utf8');print(json.dumps({k:v for k,v in result.items() if k not in ['samples','native_scene_comparisons']},indent=2),flush=True);print(json.dumps(native,indent=2),flush=True)
