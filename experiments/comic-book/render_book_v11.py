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
out=root/'v11';out.mkdir(exist_ok=True)
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
def leaf(index,side,t):
 eid=lines[index][side];source=events[eid]['scene'];style=styles[index];motion=motions[(index+side)%len(motions)]
 if motion=='parallax' and source!=3:motion='in'
 if style=='breakout':motion='parallax'
 if style=='sequence':motion='reveal'
 duration=pages[index]['duration'];p=max(0,min(1,t/duration));e=ease(p)
 # Alternating upper/lower paper caption areas remain separate from moving art.
 top_caption=(index+side)%2==0;art_y=154 if top_caption else 30;art_h=488;caption_y=20 if top_caption else 530
 page=Image.new('RGB',(PW,PH),'#f7f2e8');d=ImageDraw.Draw(page)
 for slot,(nx,ny,nw,nh) in enumerate(rects(style)):
  x=round(14+nx*(PW-28));y=round(art_y+ny*art_h);w=round(nw*(PW-28));h=round(nh*art_h)
  panel_source=(source+slot-1)%10+1 if style in ('grid','grid6','asymmetric','wide','long','parallel','borderless') else source
  im=images[panel_source];z=1.0;cx=.5;cy=.4 if panel_source in (3,4,5,8,10) else .55
  if motion=='in':z=1+.22*e
  elif motion=='out':z=1.22-.22*e
  elif motion in ('left','right'):z=1.3;cx=.3+.4*(e if motion=='right' else 1-e)
  elif motion in ('up','down'):cy=.25+.45*(e if motion=='down' else 1-e)
  elif motion=='diagonal':z=1+.2*e;cx=.35+.25*e;cy=.6-.3*e
  elif motion=='punch':z=1+.28*ease(min(1,p/.2))
  elif motion=='shake':z=1.08;cx+=.012*max(0,1-t)*math.sin(t*63);cy+=.012*max(0,1-t)*math.cos(t*49)
  if style in ('sequence','grid','grid6'):z+=.16*slot;cx+=.07*(slot%2);cy=max(.2,min(.75,cy+.08*(slot-1)))
  panel=crop(im,(w,h),z,cx,cy)
  if motion=='focus':panel=Image.blend(panel.filter(ImageFilter.GaussianBlur(5)),panel,e)
  if motion=='parallax' or style=='breakout':
   panel=crop(images[1],(w,h),1.15,.4+.13*e,.5)
  if motion=='reveal' and p<slot*.18:panel=Image.new('RGB',(w,h),'#ded6c6')
  if style=='diagonal':
   mask=Image.new('L',(w,h));ImageDraw.Draw(mask).polygon([(0,0),(w,0),(0,h)] if slot==0 else [(w,5),(w,h),(5,h)],fill=255)
   page.paste(panel,(x,y),mask);d.line((x+w,y,x,y+h),fill='#252525',width=3)
  else:
   page.paste(panel,(x,y))
   if style not in ('borderless','bleed'):d.rectangle((x,y,x+w-1,y+h-1),outline='#272522',width=2)
  if motion=='parallax' and style!='breakout':
   fg=ImageOps.contain(foreground,(int(w*.75),h-12));panel_layer=Image.new('RGBA',(w,h));panel_layer.paste(fg,(int(w*.2-w*.08*e),6),fg);page.paste(panel_layer,(x,y),panel_layer)
 if style=='breakout':
  # Extends past the inner frame, but never out of the physical 3:4 page/art area.
  fg=ImageOps.contain(foreground,(PW-20,art_h+18));page.paste(fg,(int((PW-fg.width)/2+8*math.sin(p*math.pi)),art_y-8),fg)
 if style=='inset' or motion=='inset':
  q=ease(max(0,min(1,(p-.2)/.15)))
  if q>0:
   w=max(1,int(220*q));h=max(1,int(180*q));detail=crop(images[source],(w,h),1.6,.5,.5);x=PW-w-22;y=art_y+art_h-h-12
   page.paste(detail,(x,y));d.rectangle((x,y,x+w,y+h),outline='white',width=5)
 elapsed=t-local_starts[index][side]
 if elapsed>=0:
  _,balloon,position=captions[index,side][0]
  balloon,position=animated_balloon(balloon,position,elapsed,events[eid]['kind']=='dialogue')
  page.paste(balloon,(position[0],caption_y+position[1]),balloon)
 d.text((16,PH-22),f'{index*2+side+1:02}  {labels[index]}',font=label_font,fill='#5b5145')
 return page
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
manifest={'duration':130,'page_size':[PW,PH],'book_offset':[X,Y],'pages':pages,'layouts':styles,'motion_effects':motions,'sound_duration_multiplier':1.15,'turn_duration':turn,'new_ai_generations':0}
(out/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf8')
buttons=''.join(f'<button onclick="seek({p["start"]})">{i+1:02} {labels[i]}</button>' for i,p in enumerate(pages))
html=f'''<!doctype html><meta charset="utf-8"><title>낡은 검보 · 세로 만화책 통합본</title><style>body{{margin:24px;background:#111;color:#eee;font:16px system-ui}}main{{max-width:1280px;margin:auto}}video{{width:100%;background:black}}nav{{display:flex;flex-wrap:wrap;gap:8px;margin:20px 0}}button{{padding:12px;background:#344440;color:white;border:0;border-radius:6px}}p{{line-height:1.7;color:#c3c8c5}}</style><main><h1>낡은 검보 · 3:4 세로 페이지 통합본</h1><p>좌우 각 페이지 504×672 (3:4), 총 26페이지 · 영상 2:10.<br>검은 바깥 여백 · 책등을 넘지 않는 컷 · 이미지 모션 · 인셋·경계 돌파 · 대사 말풍선 팝 · 나레이션 상자 · 3D 책장 넘김.<br>책장 소리 4종은 길이를 15% 늘려 순환합니다. 음성 높이는 유지하며 넘김 동작은 약 1.21초입니다.</p><video id="v" controls src="output.mp4" poster="page_01.png"></video><nav>{buttons}</nav></main><script>function seek(t){{const v=document.getElementById('v');v.currentTime=t;v.play()}}</script>'''
(out/'index.html').write_text(html,encoding='utf8');print('DONE 130 seconds',flush=True)
