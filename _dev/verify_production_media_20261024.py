import json,subprocess,hashlib,re
from pathlib import Path
import numpy as np
base=Path('D:/AIRStudio/verification/production-submit-20261024');job=json.loads((base/'normal/job.json').read_text(encoding='utf8'));out=Path('D:/AIRStudio/motion-render-media/c8640bf7-b6a8-4696-b988-2924190f5d30/final/output.mp4');ff=str(Path('auth-web/node_modules/ffmpeg-static/ffmpeg.exe').resolve())
info=subprocess.run([ff,'-hide_banner','-i',str(out)],capture_output=True,text=True).stderr;duration=re.search(r'Duration: (\d+):(\d+):([\d.]+)',info);h,m,s=map(float,duration.groups());duration=h*3600+m*60+s
frames=subprocess.check_output([ff,'-v','error','-i',str(out),'-t','6.20','-an','-f','framemd5','-']).decode();hashes=[l.rsplit(',',1)[-1].strip() for l in frames.splitlines() if l and not l.startswith('#')]
report={'file':str(out),'sha256_matches_uploaded':hashlib.sha256(out.read_bytes()).hexdigest()==job['final']['sha256'],'duration':duration,'required_duration':12.434285714285704,'video_frames_checked':len(hashes),'unique_frames':len(set(hashes)),'review_skipped':job['review']['skipped'],'all_scene_reviews_skipped':all(r['review']['skipped'] for r in job['results'])}
subprocess.run([ff,'-v','error','-i',str(out),'-f','null','-'],check=True)
def frame(p):return np.frombuffer(subprocess.check_output([ff,'-v','error','-ss','1','-i',str(p),'-frames:v','1','-vf','scale=640:360','-pix_fmt','rgb24','-f','rawvideo','-']),dtype=np.uint8).reshape(360,640,3).astype(float)
raw=frame(base/'normal.mp4');render=frame(out);ys,xs=np.ogrid[:360,:640];mask=((xs-320)/320)**2+((ys-180)/180)**2>1.3;center=((xs-320)/320)**2+((ys-180)/180)**2<.15
report['effect_pixel_measurement']={'edge_darkening_mean':float((raw-render)[mask].mean()),'center_darkening_mean':float((raw-render)[center].mean())}
assert report['sha256_matches_uploaded'] and report['all_scene_reviews_skipped'];assert abs(duration-report['required_duration'])<.12;assert len(hashes)==len(set(hashes))
report['full_decode']='passed';(base/'normal/media-check.json').write_text(json.dumps(report,indent=2),encoding='utf8');print(json.dumps(report))
