from pathlib import Path
import sys,json,subprocess
sys.path.insert(0,str(Path(__file__).resolve().parent))
from render_3373_ae_final import RUN
import imageio_ffmpeg
from PIL import Image, ImageDraw
ff=imageio_ffmpeg.get_ffmpeg_exe();out=RUN/'output.mp4'
g=imageio_ffmpeg.read_frames(str(out));info=next(g);g.close()
assert info.get('audio_codec')=='aac' and info['size']==(1920,1080) and abs(info['duration']-800.07)<2
sheet=Image.new('RGB',(1280,4*390),'#181818');draw=ImageDraw.Draw(sheet)
for i,sec in enumerate([2,20,60,105,175,190,400,795]):
    target=RUN/f'qa_{sec:03d}.jpg'
    p=subprocess.run([ff,'-v','error','-ss',str(sec),'-i',str(out),'-frames:v','1','-y',str(target)],capture_output=True,timeout=30)
    assert p.returncode==0,p.stderr
    im=Image.open(target).convert('RGB');im.thumbnail((640,360));x=(i%2)*640;y=(i//2)*390;sheet.paste(im,(x,y+30));draw.text((x+10,y+7),f'{sec}s',fill='white')
sheet.save(RUN/'final_contact.jpg',quality=92)
r=subprocess.run([ff,'-hide_banner','-i',str(out),'-af','volumedetect','-vn','-f','null','-'],capture_output=True,timeout=120)
assert r.returncode==0
(RUN/'audio_qa.log').write_bytes(r.stderr)
(RUN/'final_qa.json').write_text(json.dumps(info,default=str,indent=2),encoding='utf-8')
print('VERIFIED_FINAL',info['duration'],info['audio_codec'],flush=True)
