import os,json,subprocess,numpy as np
from pathlib import Path
out=Path('output/motion-fullbody-validation');ff=os.environ.get('MOTION_FFMPEG','ffmpeg');r=json.loads((out/'verification.json').read_text(encoding='utf-8'))
def decode(f):return np.frombuffer(subprocess.check_output([ff,'-v','error','-i',str(f),'-vn','-ar','48000','-ac','1','-f','f32le','-']),dtype='<f4')
a=np.concatenate([decode(out/f"scene-{s['scene']}.wav") for s in r['offsets']]);b=decode(r['file']);best=(-1,0)
for lag in range(-50,51):
 x=a[max(0,-lag)*48::48];y=b[max(0,lag)*48::48];size=min(len(x),len(y));best=max(best,(float(np.corrcoef(x[:size],y[:size])[0,1]),lag))
assert best[0]>.97,best
assert abs(len(b)-len(a))/48000<.1
for s in r['offsets']:
 for i,t in enumerate([s['start']+.1,(s['start']+s['end'])/2,s['end']-.1]):subprocess.check_call([ff,'-v','error','-y','-ss',str(t),'-i',r['file'],'-frames:v','1','-vf','scale=640:360',str(out/f"encoded-{s['scene']}-{i}.png")])
qa={'best_correlation':best[0],'lag_ms_at_1ms_resolution':best[1],'source_samples':len(a),'output_samples':len(b),'trailing_duration_difference_seconds':(len(b)-len(a))/48000,'full_decode_passed':True};(out/'audio-qa.json').write_text(json.dumps(qa,indent=2),encoding='utf-8');print(json.dumps(qa))
