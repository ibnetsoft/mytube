import argparse,json,subprocess
from pathlib import Path
import imageio_ffmpeg,numpy as np
from PIL import Image,ImageDraw
ROOT=Path(__file__).resolve().parents[1]
parser=argparse.ArgumentParser();parser.add_argument('--directory',type=Path,default=ROOT/'output/effectcraft/psd-3376-scene25-20261021');parser.add_argument('--times',default='0,.5,1,2,3,4,7,9.958333');args=parser.parse_args()
D=args.directory.resolve()
FF=imageio_ffmpeg.get_ffmpeg_exe()
times=[float(t) for t in args.times.split(',')]
rows=[]
sheet=Image.new('RGB',(1280,len(times)*385),'#151515');draw=ImageDraw.Draw(sheet)
for i,t in enumerate(times):
    frames=[]
    for name in ['ae-reference','effectcraft']:
        path=D/f'{name}-{i}.png'
        subprocess.run([FF,'-y','-v','error','-ss',str(t),'-i',str(D/(name+'.mp4')),'-frames:v','1',str(path)],check=True)
        im=Image.open(path).convert('RGB');frames.append(np.asarray(im).astype(float))
        x=0 if name=='ae-reference' else 640
        sheet.paste(im.resize((640,360)),(x,i*385+25))
        draw.text((x+10,i*385+7),f'{name} | {t:.3f}s',fill='white')
    a,b=frames;mae=float(np.abs(a-b).mean());mse=float(((a-b)**2).mean())
    rows.append(dict(time=t,mae_8bit=mae,psnr_db=float(10*np.log10(255**2/max(mse,1e-10)))))
sheet.save(D/'comparison-contact.jpg',quality=93)
for name in ['ae-reference','effectcraft']:
    count,seconds=imageio_ffmpeg.count_frames_and_secs(str(D/(name+'.mp4')))
    print(name,count,seconds,flush=True)
(D/'frame-metrics.json').write_text(json.dumps(rows,indent=2))
print(json.dumps(rows),flush=True)
subprocess.run([FF,'-y','-v','error','-i',str(D/'ae-reference.mp4'),'-i',str(D/'effectcraft.mp4'),'-filter_complex','[0:v]scale=960:540,drawtext=text=AE:x=20:y=20:fontsize=28:fontcolor=white:box=1:boxcolor=black[a];[1:v]scale=960:540,drawtext=text=EffectCraft:x=20:y=20:fontsize=28:fontcolor=white:box=1:boxcolor=black[b];[a][b]hstack=inputs=2[v]','-map','[v]','-an','-c:v','libx264','-crf','18','-preset','fast',str(D/'side-by-side.mp4')],check=True)
