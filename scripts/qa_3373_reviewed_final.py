import json,hashlib,subprocess
from pathlib import Path
from PIL import Image,ImageDraw
import numpy as np,imageio_ffmpeg
P=Path('output/project-recovery-e9233112');D=P/'reviewed-final-local';cfg=json.loads((D/'config.json').read_text(encoding='utf8'));out=D/'output.mp4';ff=imageio_ffmpeg.get_ffmpeg_exe();gen=imageio_ffmpeg.read_frames(str(out));info=next(gen);gen.close();assert info['size']==(1920,1080) and info.get('audio_codec');assert abs(info['duration']-cfg['audio_duration'])<.2
subprocess.run([ff,'-v','error','-i',str(out),'-f','null','-'],check=True,capture_output=True)
report=[];panels=[]
def grey(im):return np.asarray(im.resize((96,54)).convert('L'),dtype=float)[12:43,:].ravel()
for i,(n,name) in enumerate(zip(cfg['scene_numbers'],cfg['images'])):
 start=cfg['image_timing_starts'][i];end=cfg['image_timing_starts'][i+1] if i<100 else cfg['audio_duration'];sec=(start+end)/2;dest=D/f'final-scene-{n:03}.jpg';subprocess.run([ff,'-y','-v','error','-ss',str(sec),'-i',str(out),'-frames:v','1',str(dest)],check=True,capture_output=True)
 src=D/'images'/name
 if src.suffix=='.mp4':src=D/f'source-review-{n}.jpg'
 im=Image.open(dest).convert('RGB');ref=Image.open(src).convert('RGB');corr=float(np.corrcoef(grey(im),grey(ref))[0,1]);report.append({'scene':n,'time':sec,'source_correlation':round(corr,4)})
 im.thumbnail((300,169));panel=Image.new('RGB',(310,195),'#171717');panel.paste(im,(5,22));ImageDraw.Draw(panel).text((8,3),f'{n} / {sec:.1f}s / {corr:.2f}',fill='white');panels.append(panel)
for group in range(6):
 sheet=Image.new('RGB',(1550,780),'#111111')
 for i,panel in enumerate(panels[group*20:(group+1)*20]):sheet.paste(panel,((i%5)*310,(i//5)*195))
 sheet.save(D/f'final-review-sheet-{group}.jpg')
for n in [22,23,24,25,30,31,32,33,34]:
 assert cfg['render_settings']['scene_motion_speeds'][n-1]==1
result={'passed':False,'technical_passed':True,'duration':info['duration'],'size':out.stat().st_size,'sha256':hashlib.sha256(out.read_bytes()).hexdigest(),'subtitles':len(cfg['subtitles']),'scenes':len(cfg['images']),'scene_checks':report,'needs_visual_review':[r['scene'] for r in report if r['source_correlation']<.75]}
(P/'reviewed-final-qa.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8');print(json.dumps({k:v for k,v in result.items() if k!='scene_checks'}),flush=True)
