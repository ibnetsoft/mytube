"""Integrated portrait-page comic experiment, 130 seconds, no AI generation."""
import sys,json,math,subprocess
from pathlib import Path
import numpy as np
from PIL import Image,ImageDraw,ImageFont,ImageOps,ImageFilter
from moviepy import VideoClip,AudioFileClip,CompositeAudioClip
from imageio_ffmpeg import get_ffmpeg_exe
root=Path(__file__).resolve().parent;sys.path.insert(0,str(root.parents[1]))
from services.comic_page_turn import page_curl
from services.comic_lettering import caption_layers
from services.comic_render_service import animated_balloon
from services.comic_turn_audio import recorded_page_turns
out=root/'v12';out.mkdir(exist_ok=True)
PW,PH=504,672;BW=PW*2;X,Y=(1280-BW)//2,(720-PH)//2
assert PW/PH==3/4
fontpath=str(root.parents[1]/'auth-web/public/fonts/NanumSquareExtraBold.ttf')
label_font=ImageFont.truetype(fontpath,16)
events={e['id']:e for e in json.loads((root/'v2/events.json').read_text(encoding='utf8'))}
images={i:Image.open(root/'images'/f'scene_{i:02}.png').convert('RGB') for i in range(1,11)}
foreground=Image.open(root/'v4/foreground.png').convert('RGBA')
styles=['grid','grid6','asymmetric','wide','long','diagonal','splash','parallel','borderless','bleed','breakout','sequence','inset']
labels=['격자 2×2','격자 2×3','비대칭','가로 컷 · 페이지 안','세로 컷','대각선','스플래시','대응·평행','테두리 없음','블리드','경계 돌파 · 페이지 안','연속 컷','인셋 컷']
lines=[('01-n','02-n'),('03-n','03-d0'),('04-n','04-d0'),('05-n','05-d0'),('06-n','07-n'),('07-d0','08-n'),('08-d0','09-n'),('09-d0','10-n'),('10-d0','10-d1'),('01-n','03-d0'),('03-n','03-d0'),('10-n','10-d0'),('07-n','07-d0')]
motions=['in','out','left','right','up','down','diagonal','focus','parallax','shake','reveal','punch','inset']
clips=[];base=[]
for pair in lines:
 lengths=[]
 for eid in pair:
  c=AudioFileClip(str(root/'v2'/f'{eid}.wav'));clips.append(c);lengths.append(c.duration+.45)
 base.append(sum(lengths))
fps=24;turn_frames=29;turn=turn_frames/fps;budget=130*fps-12*turn_frames
raw=np.array(base)/sum(base)*budget;counts=np.floor(raw).astype(int)
for i in np.argsort(-(raw-counts))[:budget-sum(counts)]:counts[i]+=1
pages=[];tracks=[];local_starts=[];clock=0
for i,pair in enumerate(lines):
 duration=int(counts[i])/fps;speed=base[i]/duration;offset=0;starts=[]
 for j,eid in enumerate(pair):
  clip=clips[i*2+j];dest=out/f'voice_{i}_{j}.wav'
  subprocess.run([get_ffmpeg_exe(),'-y','-i',str(root/'v2'/f'{eid}.wav'),'-af',f'atempo={speed:.12f}','-ar','44100',str(dest)],check=True,capture_output=True)
  processed=AudioFileClip(str(dest));tracks.append(processed.with_start(clock+offset+.12));starts.append(offset+.12)
  offset+=(clip.duration+.45)/speed
 pages.append({'start':clock,'end':clock+duration,'duration':duration,'layout':styles[i]});local_starts.append(starts);clock+=duration+(turn if i<12 else 0)
sound_paths=[]
for i in range(1,5):
 dest=out/f'page-turn-{i:02}-115pct.wav'
 subprocess.run([get_ffmpeg_exe(),'-y','-i',str(root/'page-turn-audio'/f'page-turn-{i:02}.mp3'),'-af',f'atempo={1/1.15:.12f},apad,atrim=duration=1.1845','-ar','44100',str(dest)],check=True,capture_output=True);sound_paths.append(dest)
sounds,sound_resources=recorded_page_turns(sound_paths,pages,turn,.55);tracks+=sounds
def ease(t):return t*t*(3-2*t)
def crop(im,size,z=1,cx=.5,cy=.5):
 w,h=im.size;ch=min(h,w/(size[0]/size[1]))/z;cw=ch*size[0]/size[1]
 x=max(0,min(w-cw,cx*w-cw/2));y=max(0,min(h-ch,cy*h-ch/2))
 return im.transform(size,Image.Transform.EXTENT,(x,y,x+cw,y+ch),Image.Resampling.BICUBIC)
def rects(style):
 if style=='grid':return [(0,0,.49,.49),(.51,0,.49,.49),(0,.51,.49,.49),(.51,.51,.49,.49)]
 if style=='grid6':return [(c*.51,r*.34,.49,.32) for r in range(3) for c in range(2)]
 if style=='asymmetric':return [(0,0,1,.62),(0,.64,.49,.36),(.51,.64,.49,.36)]
 if style=='wide':return [(0,r*.34,1,.32) for r in range(3)]
 if style=='long':return [(0,0,.49,1),(.51,0,.49,1)]
 if style=='diagonal':return [(0,0,1,1)]*2
 if style in ('parallel','borderless'):return [(0,0,1,.49),(0,.51,1,.49)]
 if style=='sequence':return [(0,r*.255,1,.235) for r in range(4)]
 return [(0,0,1,1)]
captions={}
for i,pair in enumerate(lines):
 for side,eid in enumerate(pair):
  e=events[eid];blocks=[{'text':e['text'],'start':0,'dialogue_kind':e['kind'],'comic':{'kind':e['kind'],'style':e.get('style','speech'),'x':.04,'y':.1,'width':.92,'target_x':.5,'target_y':0}}]
  captions[i,side]=caption_layers((PW,132),blocks,fontpath,19)
import editorial_v12
editorial_v12.install(globals().copy())
leaf=editorial_v12.leaf

def spread(i,t):
 book=Image.new('RGB',(BW,PH));book.paste(leaf(i,0,t),(0,0));book.paste(leaf(i,1,t),(PW,0))
 d=ImageDraw.Draw(book)
 for off in range(-5,6):d.line((PW+off,0,PW+off,PH),fill=tuple(int(170+abs(off)*12) for _ in range(3)))
 return np.array(book)
cache={}
def frame(t):
 i=next((i for i,p in enumerate(pages) if t<p['end']+(turn if i<12 else 0)),12);p=pages[i]
 if t>=p['end'] and i<12:
  if cache.get('i')!=i:cache.update(i=i,a=spread(i,p['duration']),b=spread(i+1,0))
  book=page_curl(cache['a'],cache['b'],(t-p['end'])/turn)
 else:book=spread(i,t-p['start'])
 canvas=np.zeros((720,1280,3),dtype=np.uint8);canvas[Y:Y+PH,X:X+BW]=book;return canvas
for i,p in enumerate(pages):Image.fromarray(frame(p['end']-.001)).save(out/f'page_{i+1:02}.png')
assert abs(clock-130)<1e-6
if '--preview' in sys.argv:print('PREVIEW READY');sys.exit(0)
from proglog import ProgressBarLogger
class Log(ProgressBarLogger):
 last=-1
 def bars_callback(self,bar,attr,value,old_value=None):
  if bar=='frame_index' and attr=='index':
   n=int(value/max(1,self.bars[bar].get('total',1))*10)
   if n!=self.last:print('render',n*10,'%',flush=True);self.last=n
mix=CompositeAudioClip(tracks).with_duration(130);video=VideoClip(frame,duration=130).with_audio(mix)
video.write_videofile(str(out/'output.mp4'),fps=24,codec='libx264',audio_codec='aac',preset='veryfast',threads=2,logger=Log(),ffmpeg_params=['-pix_fmt','yuv420p','-movflags','+faststart'])
video.close();mix.close()
for c in clips+sound_resources:c.close()
manifest={'duration':130,'page_size':[PW,PH],'book_offset':[X,Y],'pages':pages,'layouts':styles,'motion_effects':motions,'sound_duration_multiplier':1.15,'turn_duration':turn,'new_ai_generations':0,'editorial_pages':[{'spread':i+1,'left':editorial_v12.plans[i,0],'right':editorial_v12.plans[i,1]} for i in range(13)]}
(out/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf8')
buttons=''.join(f'<button onclick="seek({p["start"]})">{i+1:02} 장면 {i+1}</button>' for i,p in enumerate(pages))
html=f'''<!doctype html><meta charset="utf-8"><title>낡은 검보 · 세로 만화책 통합본</title><style>body{{margin:24px;background:#111;color:#eee;font:16px system-ui}}main{{max-width:1280px;margin:auto}}video{{width:100%;background:black}}nav{{display:flex;flex-wrap:wrap;gap:8px;margin:20px 0}}button{{padding:12px;background:#344440;color:white;border:0;border-radius:6px}}p{{line-height:1.7;color:#c3c8c5}}</style><main><h1>낡은 검보 · 웹툰식 재편집</h1><p>좌우 각 페이지 504×672 (3:4), 총 26페이지 · 영상 2:10.<br>비대칭 컷·여백과 경계에 걸친 연결 말풍선·컷별 서로 다른 모션·좌우 원본 이미지 중복 없음·3D 책장 넘김.<br>책장 소리 4종은 길이를 15% 늘려 순환합니다. 음성 높이는 유지하며 넘김 동작은 약 1.21초입니다.</p><video id="v" controls src="output.mp4" poster="page_01.png"></video><nav>{buttons}</nav></main><script>function seek(t){{const v=document.getElementById('v');v.currentTime=t;v.play()}}</script>'''
(out/'index.html').write_text(html,encoding='utf8');print('DONE 130 seconds',flush=True)
