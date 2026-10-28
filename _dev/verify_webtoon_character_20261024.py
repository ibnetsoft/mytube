"""Native isolated diagnostic; no production project or AI output review."""
import sys,json,hashlib,runpy
from pathlib import Path
root=Path(__file__).resolve().parents[1];sys.path[:0]=[str(root),str(root/'worker')]
from dotenv import load_dotenv
load_dotenv(root/'.env')
from horizontal_webtoon import render
from ae_mouth_runtime import instance_lock
import worker_config
from PIL import Image
import numpy as np
from moviepy import VideoFileClip
helpers=runpy.run_path(str(root/'tests/test_horizontal_webtoon.py'))
directory=Path('D:/AIRStudio/verification/webtoon-character-20261024');directory.mkdir(parents=True,exist_ok=True)
source=helpers['layered_source'](directory);plan=helpers['character_plan']()
bound={'source_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),'plan':plan}
with instance_lock(worker_config.STATE_DIR/'motion_automation_worker.lock'):
    output=render(source,bound,directory,3,24,lambda:None)
with VideoFileClip(str(output),audio=False) as video:
    start=video.get_frame(0);end=video.get_frame(2.9)
    Image.fromarray(start).save(directory/'start.png');Image.fromarray(end).save(directory/'end.png')
    diff=np.abs(start.astype(float)-end.astype(float)).mean(axis=2)
    # Character turquoise pixels against an independent fixed dark background.
    def center(frame):
        mask=(frame[:,:,1]>90)&(frame[:,:,2]>90)&(frame[:,:,0]<60)
        y,x=np.where(mask);return [float(x.mean()),float(y.mean())]
    first,last=center(start),center(end)
    report={'output':str(output),'duration':video.duration,'fps':video.fps,'start_center':first,'end_center':last,'movement_pixels':float(np.linalg.norm(np.array(first)-last)),'background_mean_change':float(diff[50:200,100:500].mean()),'review':'not_performed_technical_diagnostic_only'}
    assert report['movement_pixels']>10 and report['background_mean_change']<1
(directory/'verification.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
print(json.dumps(report),flush=True)

# Exercise the same native renderer with two cuts of one continuously playing clip.
import subprocess
from ae_media_utils import ffmpeg
video_dir=directory/'video';video_dir.mkdir(exist_ok=True)
clip=video_dir/'source.mp4'
subprocess.run([ffmpeg(),'-v','error','-y','-f','lavfi','-i','testsrc2=size=640x360:rate=24:duration=3','-c:v','libx264','-pix_fmt','yuv420p',str(clip)],check=True)
p=helpers['character_plan']();p.pop('layer_motion');panel=p['shots'][0]['panels'][0]
p['shots']=[{'start':0,'end':.5,'panels':[panel]},{'start':.5,'end':1,'panels':[dict(panel)]}]
with instance_lock(worker_config.STATE_DIR/'motion_automation_worker.lock'):
    rendered=render(clip,{'source_sha256':hashlib.sha256(clip.read_bytes()).hexdigest(),'plan':p},video_dir,2,24,lambda:None)
with VideoFileClip(str(rendered),audio=False) as result,VideoFileClip(str(clip),audio=False) as original:
    errors=[];matches=[]
    source_frames=[f.astype(float) for f in original.iter_frames()]
    for t in (.25,.75,1.25,1.75):
        actual=np.asarray(Image.fromarray(result.get_frame(t)).resize((640,360))).astype(float)
        expected=original.get_frame(t).astype(float)
        errors.append(float(np.abs(actual-expected).mean()))
        matches.append(int(np.argmin([np.abs(actual-f).mean() for f in source_frames])))
    hashes=[hashlib.sha256(f.tobytes()).hexdigest() for f in result.iter_frames()]
    proof={'output':str(rendered),'duration':result.duration,'source_duration':original.duration,'sample_mae':errors,'unique_frames':len(set(hashes)),'frames':len(hashes),'matched_source_frames':matches,'continuous_clock_across_cuts':matches==[6,18,30,42]}
    assert matches==[6,18,30,42] and len(set(hashes))==len(hashes)
(video_dir/'verification.json').write_text(json.dumps(proof,indent=2),encoding='utf-8')
print(json.dumps(proof),flush=True)
