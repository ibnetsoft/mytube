import json,os,subprocess,math,re,time,numpy as np
from pathlib import Path
out=Path('output/motion-longform-validation');ff=os.environ.get('MOTION_FFMPEG','ffmpeg');receipt=json.loads((out/'render-receipt.json').read_text(encoding='utf-8'));manifest=json.loads((out/'source-manifest.json').read_text(encoding='utf-8'));video=receipt['file'];duration=manifest['rows'][-1]['end'];expected=math.ceil(duration*24);frames=set([0,expected-1]);labels=[]
for s in manifest['rows']:
 frames.add(min(expected-1,math.ceil((s['start']+s['end'])/2*24)))
 if s['start']>0:
  frames.add(max(0,math.ceil(s['start']*24)-1));frames.add(math.ceil(s['start']*24))
indices=sorted(frames);expr='+'.join(f'eq(n,{n})' for n in indices);started=time.time();print('Decode all streams and extract '+str(len(indices))+' scene/boundary samples',flush=True)
p=subprocess.run([ff,'-v','error','-y','-i',video,'-map','0:v:0','-map','0:a:0','-f','null','NUL','-map','0:v:0','-vf',f"select='{expr}',scale=480:270",'-fps_mode','vfr','-q:v','3',str(out/'sample-%04d.jpg'),'-progress','pipe:1'],capture_output=True,text=True);(out/'decode-errors.txt').write_text(p.stderr,encoding='utf-8');assert p.returncode==0,p.stderr;assert not p.stderr.strip(),p.stderr
samples=list(out.glob('sample-*.jpg'));assert len(samples)==len(indices),(len(samples),len(indices));(out/'sample-index.json').write_text(json.dumps([{'file':str(out/f'sample-{i+1:04d}.jpg'),'frame':n,'time':n/24,'scene':next(s['number'] for s in manifest['rows'] if s['start']<=n/24<s['end'])} for i,n in enumerate(indices)],indent=2),encoding='utf-8')
crc=subprocess.check_output([ff,'-v','error','-i',video,'-map','0:v:0','-c','copy','-f','framecrc','-'],text=True);(out/'video-packets.txt').write_text(crc,encoding='utf-8');packets=[line.split(',') for line in crc.splitlines() if line and not line.startswith('#')];assert len(packets)==expected,(len(packets),expected);pts=[int(p[2]) for p in packets];dts=[int(p[1]) for p in packets];assert all(b>a for a,b in zip(dts,dts[1:])), 'Nonmonotonic decode timestamps';assert len(set(pts))==expected, 'Repeated presentation timestamps'
def audio(f):return np.frombuffer(subprocess.check_output([ff,'-v','error','-i',str(f),'-vn','-ac','1','-ar','8000','-f','f32le','-']),dtype='<f4')
a=audio(manifest['audio']['file']);b=audio(video);assert abs(len(b)-len(a))/8000<.15;best=(-1,0)
for lag in range(-30,31):
 x=a[max(0,-lag)*8::8];y=b[max(0,lag)*8::8];n=min(len(x),len(y));best=max(best,(float(np.corrcoef(x[:n],y[:n])[0,1]),lag))
assert best[0]>.97,best;windows=[]
for start in range(0,int(duration),60):
 end=min(start+60,duration);x=a[int(start*8000):int(end*8000)];y=b[int(start*8000):int(end*8000)];n=min(len(x),len(y));c=float(np.corrcoef(x[:n],y[:n])[0,1]);windows.append({'start':start,'end':end,'correlation':c});assert c>.95,(start,c)
qa={'duration_seconds':duration,'frames':len(packets),'expected_frames':expected,'unique_presentation_timestamps':True,'monotonic_decode_timestamps':True,'full_video_audio_decode':True,'sample_frames':len(indices),'audio_correlation':best[0],'best_lag_ms':best[1],'audio_padding_seconds':(len(b)-len(a))/8000,'minute_windows':windows,'render_seconds':receipt['elapsed_ms']/1000,'file_bytes':receipt['bytes'],'lazy_load_count':len(receipt['loads']),'release_count':len(receipt['releases']),'opfs':receipt['opfs'],'qa_seconds':time.time()-started};assert receipt['loads']==receipt['releases'] and len(receipt['loads'])==100;(out/'qa.json').write_text(json.dumps(qa,indent=2),encoding='utf-8');print(json.dumps({k:v for k,v in qa.items() if k!='minute_windows'},indent=2))
