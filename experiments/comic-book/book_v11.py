import sys,json,math,shutil
from pathlib import Path
import numpy as np
from PIL import Image,ImageDraw,ImageFont,ImageFilter,ImageOps
from moviepy import VideoClip,AudioFileClip,CompositeAudioClip
root=Path(__file__).resolve().parent;sys.path.insert(0,str(root.parents[1]))
from services.comic_page_turn import page_curl
from services.comic_turn_audio import recorded_page_turns
out=root/'v10';out.mkdir(exist_ok=True)
font=ImageFont.truetype(str(root.parents[1]/'auth-web/public/fonts/NanumSquareExtraBold.ttf'),24)
small=ImageFont.truetype(str(root.parents[1]/'auth-web/public/fonts/NanumSquareExtraBold.ttf'),20)
events={e['id']:e for e in json.loads((root/'v2/events.json').read_text(encoding='utf8'))}
specs=[(1,'01-n','줌 인','검으로 천천히 접근','in'),(7,'07-n','줌 아웃','검보에서 주변 공간으로','out'),(8,'08-n','좌측 이동','고정된 컷 안에서 카메라 이동','left'),(9,'09-n','우측 이동','공간을 가로질러 탐색','right'),(3,'03-n','상향 이동','발끝에서 인물 쪽으로 시선 이동','up'),(2,'02-n','하향 이동','문패에서 바닥의 흔적으로','down'),(5,'05-n','대각선 이동 + 줌','서찰과 인물 쪽으로 접근','diagonal'),(7,'07-n','인셋 컷 등장','검보 세부를 별도 컷으로 확대','inset'),(10,'10-n','초점 이동','원본 한 장의 흐림·선명도 전환','focus'),(3,'03-n','전경·배경 시차','분리해 둔 인물과 배경을 다른 속도로 이동','parallax'),(8,'08-n','짧은 충격 흔들림','한 번의 흔들림 뒤 안정화','shake'),(10,'10-n','컷 순차 공개','세부 구도를 왼쪽부터 차례로 공개','reveal'),(3,'03-d0','빠른 접근 후 정지','강조 순간에만 짧게 확대','punch')]
images={i:Image.open(root/'images'/f'scene_{i:02}.png').convert('RGB') for i in range(1,11)}
foreground=Image.open(root/'v4/foreground.png').convert('RGBA')
focus={1:(.3,.48),2:(.45,.6),3:(.5,.32),5:(.55,.4),7:(.5,.53),8:(.48,.45),9:(.5,.5),10:(.5,.4)}
audio=[];tracks=[];pages=[];clock=0;turn=25/24
for i,(scene,eid,*_) in enumerate(specs):
 clip=AudioFileClip(str(root/'v2'/f'{eid}.wav'));audio.append(clip)
 duration=max(5.2,clip.duration+.7)
 pages.append({'start':clock,'end':clock+duration,'duration':duration,'title':specs[i][2]})
 tracks.append(clip.with_start(clock+.25));clock+=duration+(turn if i<12 else 0)
sounds,resources=recorded_page_turns([root/'page-turn-audio'/f'page-turn-{i:02}.mp3' for i in range(1,5)],pages,turn,.55)
tracks+=sounds
def smooth(p):return p*p*(3-2*p)
def crop(image,size,zoom=1,cx=.5,cy=.5):
 w,h=image.size;ratio=size[0]/size[1];ch=min(h,w/ratio)/zoom;cw=ch*ratio
 x=max(0,min(w-cw,cx*w-cw/2));y=max(0,min(h-ch,cy*h-ch/2))
 return image.transform(size,Image.Transform.EXTENT,(x,y,x+cw,y+ch),Image.Resampling.BICUBIC)
def page(index,t):
 scene,eid,title,description,kind=specs[index];p=max(0,min(1,t/pages[index]['duration']));e=smooth(p)
 im=images[scene];cx,cy=focus.get(scene,(.5,.5));zoom=1.05
 if kind=='in':zoom=1+e*.32
 elif kind=='out':zoom=1.35-e*.35
 elif kind=='left':zoom=1.45;cx=.7-.4*e
 elif kind=='right':zoom=1.45;cx=.3+.4*e
 elif kind=='up':cy=.78-.48*e
 elif kind=='down':cy=.25+.48*e
 elif kind=='diagonal':zoom=1.15+.25*e;cx=.7-.3*e;cy=.6-.25*e
 elif kind=='punch':zoom=1+.4*smooth(min(1,p/.18))
 elif kind=='shake':
  strength=.018*max(0,1-t/1.1);cx+=strength*math.sin(t*68);cy+=strength*math.cos(t*49);zoom=1.15
 panel=crop(im,(1200,530),zoom,cx,cy)
 if kind=='focus':
  blurred=panel.filter(ImageFilter.GaussianBlur(9));sharp=panel
  mask=Image.new('L',panel.size);d=ImageDraw.Draw(mask);center=int(250+700*e)
  d.ellipse((center-210,-80,center+210,610),fill=255)
  panel=Image.composite(sharp,blurred,mask.filter(ImageFilter.GaussianBlur(65)))
 if kind=='parallax':
  panel=crop(images[1],(1200,530),1.18,.4+.18*e,.45)
  fg=ImageOps.contain(foreground,(480,520));panel.paste(fg,(int(670-120*e),5),fg)
 if kind=='inset' and p>.24:
  q=smooth(min(1,(p-.24)/.12));size=(int(430*q),int(260*q))
  if min(size)>0:
   detail=crop(im,size,1.8,.53,.5);x=1200-size[0]-24;y=530-size[1]-24
   panel.paste(detail,(x,y));ImageDraw.Draw(panel).rectangle((x,y,x+size[0],y+size[1]),outline='#f7f2e8',width=7)
 if kind=='reveal':
  panel=Image.new('RGB',(1200,530),'#ddd6c7')
  for j,(x,y) in enumerate(((.26,.5),(.72,.22),(.5,.45))):
   q=max(0,min(1,(p-j*.25)/.13))
   if q:
    detail=crop(im,(388,530),1.15,x,y);panel.paste(detail.crop((0,0,round(388*q),530)),(j*406,0))
 canvas=Image.new('RGB',(1280,720),'#f7f2e8');canvas.paste(panel,(40,66));d=ImageDraw.Draw(canvas)
 d.text((40,20),f'{index+1:02} / 13  {title}',font=font,fill='#172b2d')
 d.text((40,610),description,font=small,fill='#395759')
 # Text stays outside the moving image; no face/object occlusion during camera movement.
 text=events[eid]['text'];dialogue=events[eid]['kind']=='dialogue'
 if dialogue:d.rounded_rectangle((36,648,1244,706),radius=24,fill='white',outline='#324344',width=2)
 else:d.rectangle((36,648,1244,706),fill='#eee5d2',outline='#8e806b',width=1)
 d.text((55,664),text,font=font,fill='#182224')
 return np.asarray(canvas)
cache={}
def frame(t):
 index=next((i for i,p in enumerate(pages) if t<p['end']+(turn if i<12 else 0)),12)
 p=pages[index]
 if t>=p['end'] and index<12:
  if cache.get('index')!=index:cache.update(index=index,a=page(index,p['duration']),b=page(index+1,0))
  return page_curl(cache['a'],cache['b'],(t-p['end'])/turn)
 return page(index,t-p['start'])
for i,p in enumerate(pages):Image.fromarray(page(i,p['duration']*.8)).save(out/f'page_{i+1:02}.png')
mix=CompositeAudioClip(tracks).with_duration(clock);video=VideoClip(frame,duration=clock).with_audio(mix)
from proglog import ProgressBarLogger
class Log(ProgressBarLogger):
 last=-1
 def bars_callback(self,bar,attr,value,old_value=None):
  if bar=='frame_index' and attr=='index':
   n=int(value/max(1,self.bars[bar].get('total',1))*10)
   if n!=self.last:print('render',n*10,'%',flush=True);self.last=n
video.write_videofile(str(out/'output.mp4'),fps=24,codec='libx264',audio_codec='aac',preset='veryfast',threads=2,logger=Log(),ffmpeg_params=['-pix_fmt','yuv420p','-movflags','+faststart'])
video.close();mix.close()
for a in audio+resources:a.close()
manifest={'duration':clock,'pages':pages,'effects':[{'scene':s[0],'event':s[1],'name':s[2],'effect':s[4]} for s in specs],'new_ai_generations':0,'note':'이미지 이동과 합성만 사용했습니다. 인물의 새 동작을 생성한 것은 아닙니다.'}
(out/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf8')
buttons=''.join(f'<button onclick="seek({p["start"]})">{i+1:02} {p["title"]}</button>' for i,p in enumerate(pages))
html=f'''<!doctype html><meta charset="utf-8"><title>낡은 검보 · 이미지 모션 실험</title><style>body{{background:#121b1e;color:#eee;font:16px system-ui;margin:24px}}main{{max-width:1280px;margin:auto}}video{{width:100%}}nav{{display:flex;flex-wrap:wrap;gap:8px;margin:20px 0}}button{{padding:12px;background:#28454a;color:white;border:0;border-radius:6px;cursor:pointer}}p{{line-height:1.8;color:#bbcfd0}}a{{color:#9ee3d6}}</style><main><h1>낡은 검보 · 이미지만으로 만드는 13가지 모션</h1><p>기존 그림과 분리된 인물 전경을 재사용한 별도 실험 영상입니다. AI 이미지·영상 추가 생성은 없습니다.<br>확대·축소·좌우상하·대각선 이동, 인셋 등장, 초점 이동, 시차, 흔들림, 컷 순차 공개, 빠른 접근을 비교합니다.<br>글자는 움직이는 그림 밖에 배치했고, 책장 효과음 4종은 원래 속도로 순환합니다. 인물의 실제 동작이나 입 모양을 생성한 것은 아닙니다.</p><video id="v" controls src="output.mp4" poster="page_01.png"></video><nav>{buttons}</nav><p><a href="../v9/">기존 2:10 영상</a> · <a href="output.mp4" download>실험 영상 다운로드</a></p></main><script>function seek(t){{const v=document.getElementById('v');v.currentTime=t;v.play()}}</script>'''
(out/'index.html').write_text(html,encoding='utf8');print('DONE',clock,flush=True)
