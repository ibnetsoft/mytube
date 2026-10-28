import json,subprocess,hashlib
from pathlib import Path
import numpy as np,imageio_ffmpeg
P=Path('output/project-recovery-e9233112');D=P/'audio-fixed-v11';out=D/'output.mp4';old=P/'reviewed-final-local/output.mp4';cfg=json.loads((D/'config.json').read_text(encoding='utf8'));ff=imageio_ffmpeg.get_ffmpeg_exe()
import time
for attempt in range(120):
 if 'AUDIO_FIXED_REMUX_COMPLETED' in (P/'audio-fixed-remux.log').read_text(encoding='utf8'):break
 time.sleep(5)
else:raise RuntimeError('Audio remux did not finish')
def video_hash(p):
 r=subprocess.run([ff,'-v','error','-i',str(p),'-map','0:v:0','-c:v','copy','-f','hash','-hash','sha256','-'],capture_output=True,check=True);return r.stdout.decode().strip()
a=video_hash(old);b=video_hash(out);assert a==b,'Video bytes changed'
g=imageio_ffmpeg.read_frames(str(out));info=next(g);g.close();assert abs(info['duration']-cfg['audio_duration'])<.2
subprocess.run([ff,'-v','error','-i',str(out),'-vn','-f','null','-'],check=True,capture_output=True)
for name,start,length in [('door-preview',74,12),('bgm-preview',2022,31.4)]:
 subprocess.run([ff,'-y','-v','error','-ss',str(start),'-i',str(out),'-t',str(length),'-c:v','h264_nvenc','-preset','p4','-c:a','aac',str(D/(name+'.mp4'))],check=True,capture_output=True)
q={'passed':False,'technical_passed':True,'video_stream_identical':True,'video_stream_sha256':b,'sha256':hashlib.sha256(out.read_bytes()).hexdigest(),'size':out.stat().st_size,'duration':info['duration'],'sfx':cfg['sfx_cues'],'bgm_start':cfg['render_settings']['bgm_start'],'bgm_end':cfg['render_settings']['bgm_end']}
(P/'audio-fixed-qa.json').write_text(json.dumps(q,ensure_ascii=False,indent=2),encoding='utf8');print(json.dumps({k:v for k,v in q.items() if k!='sfx'}),flush=True)
