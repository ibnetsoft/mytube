import json,subprocess,os
from pathlib import Path
import numpy as np
root=Path('_dev/artifacts/v4-performance')
report=[]
for tag in ['whispers','excited']:
    pcm=subprocess.check_output([os.environ['FFMPEG_PATH'],'-v','error','-i',str(root/f'v4-{tag}.mp3'),'-f','f32le','-ar','16000','-ac','1','pipe:1'])
    x=np.frombuffer(pcm,dtype=np.float32)
    frames=[x[i:i+640] for i in range(0,len(x)-640,320)]
    energy=np.array([np.sqrt(np.mean(f*f)) for f in frames]); active=[f for f,e in zip(frames,energy) if e>max(.002,float(energy.max())*.08)]
    correlations=[]; pitches=[]
    for f in active:
        f=(f-f.mean())*np.hanning(len(f));a=np.correlate(f,f,'full')[len(f)-1:];a=a/(a[0]+1e-10)
        lag=int(np.argmax(a[40:230]))+40; correlations.append(float(a[lag]))
        if a[lag]>.5:pitches.append(16000/lag)
    report.append({'tag':tag,'durationSeconds':len(x)/16000,'rmsDbFS':20*np.log10(float(np.sqrt(np.mean(x*x)))+1e-10),'voicedFrameRatio':sum(c>.5 for c in correlations)/len(correlations),'medianPitchHz':float(np.median(pitches)) if pitches else None})
(root/'tone-acoustics.json').write_text(json.dumps(report,indent=2),encoding='utf-8');print(json.dumps(report))
