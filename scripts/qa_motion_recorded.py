import json,subprocess,os,numpy as np
from pathlib import Path
out=Path('output/motion-final-production');ff=os.environ.get('MOTION_FFMPEG','ffmpeg')
r=json.loads((out/'recorded-motion-verification.json').read_text(encoding='utf-8'));metrics=[]
for s in r['results']:
 n=s['scene'];f=s['file'];decode=lambda file:np.frombuffer(subprocess.check_output([ff,'-v','error','-i',str(file),'-vn','-ac','1','-ar','48000','-f','f32le','-']),dtype='<f4')
 a=decode(out/f'scene-{n}-recording.wav');b=decode(f);best=(-1,None)
 for lag in range(-50,51):
  x=a[max(0,-lag)*48::48];y=b[max(0,lag)*48::48];size=min(len(x),len(y));corr=float(np.corrcoef(x[:size],y[:size])[0,1]);best=max(best,(corr,lag))
 assert best[0]>.97,(n,best)
 assert abs(len(b)-len(a))/48000<.1
 for j,t in enumerate([.1,s['duration']/2,s['duration']-.1]):subprocess.check_call([ff,'-v','error','-y','-ss',str(t),'-i',f,'-frames:v','1','-vf','scale=640:360',str(out/f'encoded-{n}-{j}.png')])
 metrics.append({'scene':n,'reference_samples':len(a),'output_samples':len(b),'best_correlation':best[0],'lag_ms':best[1],'duration_difference_seconds':(len(b)-len(a))/48000})
(out/'audio-render-check.json').write_text(json.dumps(metrics,indent=2));print(json.dumps(metrics,indent=2))
