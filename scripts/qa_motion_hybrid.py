import json,os,subprocess,math,numpy as np
from pathlib import Path
out=Path('output/motion-fullbody-validation');ff=os.environ.get('MOTION_FFMPEG','ffmpeg');r=json.loads((out/'hybrid-editor-verification.json').read_text(encoding='utf-8'));fixture=Path('output/parallax-3376-scene19-oneway/parallax-oneway-scene-019-3s.mp4')
def audio(f):return np.frombuffer(subprocess.check_output([ff,'-v','error','-i',str(f),'-vn','-ac','1','-ar','48000','-f','f32le','-']),dtype='<f4')
a=audio(out/'joined-recording.wav');b=audio(r['final_mp4']);best=(-1,0)
for lag in range(-50,51):
 x=a[max(0,-lag)*48::48];y=b[max(0,lag)*48::48];size=min(len(x),len(y));best=max(best,(float(np.corrcoef(x[:size],y[:size])[0,1]),lag))
assert best[0]>.97
assert abs(len(a)-len(b))/48000<.1
frame_checks=[]
def pixels(file,t):return np.frombuffer(subprocess.check_output([ff,'-v','error','-ss',str(t),'-i',str(file),'-frames:v','1','-vf','scale=640:360','-pix_fmt','rgb24','-f','rawvideo','-']),dtype=np.uint8).reshape(360,640,3)
for i,p in enumerate(s for s in r['plan'] if s['kind']=='ai'):
 t=math.ceil((p['start']+(p['end']-p['start'])*.5)*24)/24;u=(t-p['start'])/(p['end']-p['start']);source=p['videoRange'][0]+u*(p['videoRange'][1]-p['videoRange'][0]);output=pixels(r['final_mp4'],t);scores=[]
 for f in {max(0,math.floor(source*24)-1),math.floor(source*24),math.ceil(source*24)}:
  original=pixels(fixture,f/24);scores.append((float(np.abs(output[:300].astype(float)-original[:300]).mean()),f/24))
 score=min(scores);assert score[0]<6,(p,score);frame_checks.append({'output_seconds':t,'expected_source_seconds':source,'matched_source_seconds':score[1],'mean_absolute_rgb_error':score[0]});subprocess.check_call([ff,'-v','error','-y','-ss',str(t),'-i',r['final_mp4'],'-frames:v','1',str(out/f'hybrid-insert-{i}.png')])
qa={'audio_correlation':best[0],'lag_ms_at_1ms_resolution':best[1],'trailing_padding_seconds':(len(b)-len(a))/48000,'insert_frames':frame_checks,'source_video_sha256':__import__('hashlib').sha256(fixture.read_bytes()).hexdigest(),'provenance':'retained same-project AE clip stands in for AI provider output; no generation call'};(out/'hybrid-audio-frame-qa.json').write_text(json.dumps(qa,indent=2),encoding='utf-8');print(json.dumps(qa,indent=2))
