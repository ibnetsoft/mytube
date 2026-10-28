"""Preserve native playback speed and explicitly hold the last frame to narration end."""
import hashlib,json,subprocess
from pathlib import Path
import imageio_ffmpeg,numpy as np
from PIL import Image
ROOT=Path(__file__).resolve().parents[1];D=ROOT/'output/effectcraft/project-3376-final-20261021';plan=json.loads((D/'plan.json').read_text());ff=imageio_ffmpeg.get_ffmpeg_exe();results=[]
def rgb(video,t):
    return np.frombuffer(subprocess.check_output([ff,'-v','error','-ss',str(t),'-i',str(video),'-frames:v','1','-f','rawvideo','-pix_fmt','rgb24','-']),dtype=np.uint8).reshape(1080,1920,3).astype(float)
for c in plan['clips']:
    source=Path(c['source']);assert hashlib.sha256(source.read_bytes()).hexdigest()==c['source_sha256']
    out=D/f'scene-{c["number"]}-delivery.mp4';duration=c['duration']+.6
    subprocess.run([ff,'-v','error','-y','-i',str(source),'-vf',f'tpad=stop_mode=clone:stop_duration={duration}', '-t',str(duration),'-an','-r','24','-c:v','libx264','-preset','fast','-crf','12','-threads','2','-pix_fmt','yuv420p','-color_primaries','bt709','-color_trc','bt709','-colorspace','bt709','-movflags','+faststart',str(out)],check=True)
    checks=[]
    for t in [0,.5,c['animation_duration']-1/24,c['duration']-.1]:
        expected=rgb(source,min(t,c['animation_duration']-1/24));actual=rgb(out,t);mae=float(abs(expected-actual).mean());bias=(actual-expected).mean(axis=(0,1)).tolist();assert mae<1.5,(c['number'],t,mae)
        Image.fromarray(actual.astype('uint8')).resize((960,540)).save(D/f'scene-{c["number"]}-delivery-{t:.3f}.jpg',quality=92);checks.append(dict(time=t,mae=mae,mean_rgb_bias=bias))
    results.append(dict(number=c['number'],file=str(out),sha256=hashlib.sha256(out.read_bytes()).hexdigest(),duration=duration,checks=checks,tail_policy='hold_last_frame',speed_changed=False))
    print('Scene',c['number'],'delivery ready',checks,flush=True)
(D/'padded-clips.json').write_text(json.dumps(results,indent=2))
