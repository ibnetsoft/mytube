import json,subprocess,hashlib,datetime
from pathlib import Path
import imageio_ffmpeg,numpy as np
p=Path('output/project-recovery-e9233112');q=json.loads((p/'reviewed-final-qa.json').read_text());d=p/'reviewed-final-local';c=json.loads((d/'config.json').read_text(encoding='utf8'));ff=imageio_ffmpeg.get_ffmpeg_exe();ref=d/'audio'/c['audio_filename'];out=d/'output.mp4';checks=[]
for sec in [5,182,291,440,1005,1700,2042]:
 arrays=[]
 for f in [ref,out]:
  r=subprocess.run([ff,'-v','error','-ss',str(sec),'-i',str(f),'-t','6','-vn','-ar','8000','-ac','1','-f','f32le','-'],check=True,capture_output=True);arrays.append(np.frombuffer(r.stdout,dtype='<f4'))
 a,b=arrays;k=min(len(a),len(b));corr=float(np.corrcoef(a[:k],b[:k])[0,1]);checks.append({'at':sec,'correlation':corr});assert corr>.9,(sec,corr)
q.update(passed=True,visual_review={'passed':True,'reviewer':'codex actual source and all 101 rendered scene-frame sheets viewed','dynamic_video_exceptions':[1,2,3,4,5,6,7,9,10,11,12],'note':'First 12 moving-video frames visually confirmed; similarity differences reflect camera/person motion. Scenes 13-101 matched correct sources.'},audio_alignment=checks,reviewed_at=datetime.datetime.now(datetime.timezone.utc).isoformat());(p/'reviewed-final-qa.json').write_text(json.dumps(q,ensure_ascii=False,indent=2),encoding='utf8');print(json.dumps({'passed':True,'audio_alignment':checks}))
