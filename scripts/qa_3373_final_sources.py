import json,subprocess
from pathlib import Path
from PIL import Image,ImageDraw
import imageio_ffmpeg
p=Path('output/project-recovery-e9233112/reviewed-final-local');cfg=json.loads((p/'config.json').read_text(encoding='utf8'));ff=imageio_ffmpeg.get_ffmpeg_exe();panels=[]
for n,name in zip(cfg['scene_numbers'],cfg['images']):
 src=p/'images'/name
 if src.suffix=='.mp4':
  out=p/f'source-review-{n}.jpg';subprocess.run([ff,'-y','-v','error','-ss','0.3','-i',str(src),'-frames:v','1',str(out)],check=True,capture_output=True);src=out
 im=Image.open(src).convert('RGB');im.thumbnail((300,169));panel=Image.new('RGB',(310,195),'#171717');panel.paste(im,(5,22));ImageDraw.Draw(panel).text((8,3),str(n),fill='white');panels.append(panel)
for group in range(6):
 sheet=Image.new('RGB',(1550,780),'#111111')
 for i,panel in enumerate(panels[group*20:(group+1)*20]):sheet.paste(panel,((i%5)*310,(i//5)*195))
 sheet.save(p/f'source-review-sheet-{group}.jpg')
print('SOURCE_SHEETS_READY')

