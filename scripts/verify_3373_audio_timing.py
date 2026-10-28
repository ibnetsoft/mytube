import json,subprocess
from pathlib import Path
import imageio_ffmpeg,numpy as np
P=Path('output/project-recovery-e9233112');D=P/'audio-fixed-v11';ff=imageio_ffmpeg.get_ffmpeg_exe();out=D/'output.mp4';voice=D/'audio/speech_balanced.wav';sfx=D/'audio/sfx_02_e061eaed-d1f8-4f2e-a6fd-c98122ec21f8.mp3';bgm=D/'audio/bgm_a54c031e-29e9-411b-aa55-f06a81636e6e.mp3'
def pcm(f,start,dur):
 r=subprocess.run([ff,'-v','error','-ss',str(start),'-i',str(f),'-t',str(dur),'-vn','-ar','8000','-ac','1','-f','f32le','-'],check=True,capture_output=True);return np.frombuffer(r.stdout,dtype='<f4').astype(float)
def coefficient(start,dur,asset,fade=False):
 y=pcm(out,start,dur);v=pcm(voice,start,dur);s=pcm(asset,0,dur);n=min(len(y),len(v),len(s));y=y[:n];v=v[:n];s=s[:n]
 if fade:s=s*np.minimum(1,np.arange(n)/8000/3)
 weights=np.linalg.lstsq(np.column_stack([v,s]),y,rcond=None)[0];return {'at':start,'voice_coefficient':float(weights[0]),'effect_coefficient':float(weights[1])}
checks={'door_old':coefficient(72.907,2,sfx),'door_fixed':coefficient(79.725,2,sfx),'bgm_old':coefficient(799.793,6,bgm,True),'bgm_fixed':coefficient(2026.057,6,bgm,True)}
print(json.dumps(checks),flush=True)
assert abs(checks['door_old']['effect_coefficient'])<.005
assert checks['door_fixed']['effect_coefficient']>.025
assert abs(checks['bgm_old']['effect_coefficient'])<.005
assert checks['bgm_fixed']['effect_coefficient']>.1
for name,time in [('door-start',79.9),('bgm-start',2027)]:subprocess.run([ff,'-y','-v','error','-ss',str(time),'-i',str(out),'-frames:v','1',str(D/(name+'.jpg'))],check=True,capture_output=True)
q=json.loads((P/'audio-fixed-qa.json').read_text(encoding='utf8'));q['timing_signal_checks']=checks;q['timing_verified']=True;(P/'audio-fixed-qa.json').write_text(json.dumps(q,ensure_ascii=False,indent=2),encoding='utf8')
