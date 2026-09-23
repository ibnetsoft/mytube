import json, sys, wave, shutil
from pathlib import Path
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageOps
root=Path(__file__).resolve().parent
sys.path.insert(0,str(root.parents[1]))
from services import comic_render_service as comic
out=root/'v7';out.mkdir(exist_ok=True)
font=str(root.parents[1]/'auth-web/public/fonts/NanumSquareExtraBold.ttf')
shutil.copyfile(str(root/'foreground-source.png'),out/'foreground.png')
assert Image.open(out/'foreground.png').getchannel('A').getextrema()[0]==0
original={e['id']:e for e in json.loads((root/'v2/events.json').read_text(encoding='utf8'))}
# Source art is reused; repeated scenes are layout comparisons, not new story events.
specs=[
 ('grid','정규 격자 2×2',[(1,'01-n'),(2,'02-n'),(3,'03-d0'),(4,'04-d0')]),
 ('grid6','정규 격자 2×3',[(1,'01-n'),(2,'02-n'),(3,'03-n'),(4,'04-n'),(5,'05-n'),(6,'06-n')]),
 ('asymmetric','비대칭 분할',[(7,'07-d0'),(5,'05-n'),(6,'06-n')]),
 ('wide','가로 와이드',[(1,'01-n'),(9,'09-d0')]),
 ('long','세로 롱 패널',[(3,'03-n'),(7,'07-d0'),(9,'09-n')]),
 ('diagonal','대각선 분할',[(3,'03-d0'),(8,'08-d0')]),
 ('splash','스플래시 페이지',[(7,'07-d0')]),
 ('double','양면 펼침',[(1,'01-n')]),
 ('borderless','테두리 없는 컷',[(4,'04-d0'),(5,'05-d0')]),
 ('bleed','블리드 컷',[(8,'08-n')]),
 ('breakout','경계 돌파',[(1,'03-n'),(3,'03-d0')]),
 ('sequence','연속 동작 분할',[(10,None),(10,'10-n'),(10,'10-d0'),(10,'10-d1')]),
 ('parallel','대응·평행 배치',[(4,'04-d0'),(10,'10-d0')]),
]
settings={'comic':{'version':1,'mode':'moving_comic','layout':'grid','page_layouts':{str(i):s[0] for i,s in enumerate(specs)},'turn_duration':1.1,'turn_sound':True,'font_size':22,'panels':{},'lettering':{}}}
images=[];durations=[];events=[];audio=[];refs=[];clock=0.;rate=24000
for pi,(layout,label,slots) in enumerate(specs):
 for si,(source,eid) in enumerate(slots):
  number=len(images)+1
  images.append(str(out/'foreground.png') if layout=='breakout' and si==1 else str(root/'images'/f'scene_{source:02}.png'))
  settings['comic']['panels'][str(number)]={'fit':'cover','motion':'still'}
  data=b''
  if eid:
   with wave.open(str(root/'v2'/f'{eid}.wav'),'rb') as wav:
    assert (wav.getframerate(),wav.getnchannels(),wav.getsampwidth())==(rate,1,2)
    data=wav.readframes(wav.getnframes())
   e=dict(original[eid]);e.update(start=clock+.2,end=clock+.2+len(data)/(rate*2),dialogue_kind=e['kind'],dialogue_speaker=e['speaker'],scene=number)
   events.append(e)
   cfg={'kind':e['kind'],'style':e.get('style','speech'),'x':.06,'y':.05 if e['kind']=='narration' else .66,'width':.88,'target_x':.55,'target_y':.47}
   if layout in ('grid','grid6','asymmetric'):cfg['y']=.04 if e['kind']=='narration' else .42
   if layout=='diagonal':cfg.update(x=.06 if si==0 else .58,y=.08 if si==0 else .70,width=.32,target_x=.32 if si==0 else .7,target_y=.3 if si==0 else .66)
   if layout in ('splash','double','bleed','wide'):cfg.update(width=.48,x=.05,y=.06 if e['kind']=='narration' else .67)
   if layout=='wide' and e['kind']=='dialogue':cfg['y']=.42
   if layout=='breakout':cfg.update(x=.05,y=.06 if si==0 else .69,width=.65 if si==0 else .82)
   settings['comic']['lettering'][f'{number}:0']=cfg
  duration=max(2.4,len(data)/(rate*2)+.8)
  audio.append(bytes(round(.2*rate)*2)+data+bytes(max(0,round(duration*rate)*2-round(.2*rate)*2-len(data))))
  durations.append(duration);clock+=duration
  refs.append({'cut':number,'source_image':source,'event':eid,'page':pi+1,'layout':layout})
with wave.open(str(out/'speech.wav'),'wb') as wav:
 wav.setparams((1,2,rate,0,'NONE','not compressed'));wav.writeframes(b''.join(audio))
BaseFrames=comic.ComicFrames
base_balloon=comic.balloon_layer
def checked_balloon(size,blocks,*args):
 try:return base_balloon(size,blocks,*args)
 except ValueError:
  print('FAILED BALLOON',size,[(b.get('id'),b.get('comic')) for b in blocks],flush=True);raise
comic.balloon_layer=checked_balloon
protected={1:[(.03,.03,.4,.85)],2:[(.01,.25,.85,.82)],3:[(.3,.08,.72,.45)],4:[(.08,.08,.55,.43)],5:[(.04,.02,.85,.43),(.35,.4,.95,.8)],6:[(.03,.43,.66,.67),(.56,.49,1,.72)],7:[(.01,.25,.99,.78)],8:[(.24,.03,.72,.44),(.4,.68,.82,.92)],9:[(.22,.1,.59,.37),(.02,.5,.8,.9)],10:[(.12,.38,.43,.64),(.53,.05,.89,.39)]}
placement_report=[]
class TestFrames(BaseFrames):
 def __init__(self,*a,**kw):
  super().__init__(*a,**kw)
  # Camera reframing only; source images themselves remain unchanged.
  masks=[]
  for i,ref in enumerate(refs):
   im=self.media[i];w,h=im.size
   mask=Image.new('L',im.size);md=ImageDraw.Draw(mask)
   for box in protected[ref['source_image']]:md.rectangle(tuple(round(v*(w if j%2==0 else h)) for j,v in enumerate(box)),fill=255)
   crop=None
   if ref['layout']=='sequence':
    slot=i-self.pages[11]['first']
    crops=[(.14,.25,.48,.7),(.1,.18,.55,.8),(.1,.25,.62,.92),(.48,.08,.99,.88)]
    b=crops[slot];crop=tuple(round(v*(w if j%2==0 else h)) for j,v in enumerate(b))
   elif ref['source_image']==3 and ref['layout'] in ('grid','diagonal'):
    crop=(0,0,w,round(h*.62))
   elif ref['layout'] in ('wide','splash','double','bleed'):
    # Focus wide crops on the upper/middle illustrated scene, not empty floor.
    crop=(0,round(h*.12),w,round(h*.75))
   if crop:self.media[i]=im.crop(crop);mask=mask.crop(crop);im.close()
   masks.append(mask)
  for i,ref in enumerate(refs):
   blocks=[e for e in events if e['scene']==i+1]
   if not blocks:continue
   page=self.pages[ref['page']-1];slot=i-page['first'];rect=comic.LAYOUTS[ref['layout']][slot]
   size=(round(rect[2]*1280),round(rect[3]*720));w,h=size
   mask=ImageOps.fit(masks[i],size)
   if ref['layout']=='breakout' and slot==1:
    # Protect the entire extracted foreground, including both faces and hands.
    fg=ImageOps.contain(self.media[i],size);mask=Image.new('L',size);mask.paste(fg.getchannel('A'),((w-fg.width)//2,(h-fg.height)//2))
   if ref['layout']=='breakout' and slot==0:ImageDraw.Draw(mask).rectangle((int(w*.69),0,w,h),fill=255)
   arr=np.asarray(mask)>0
   cfg=dict(settings['comic']['lettering'][f'{i+1}:0'])
   def choose(avoid):
    xs=[.03,.52,.27,.1,.65,.4,.72];ys=[.03,.78,.62,.4,.2,.85,.5,.1,.7,.75,.72,.8,.82,.6,.55]
    for bw in [.65,.45,.88,.32,.24]:
     for y in ys:
      for x in xs:
       if x+bw>.98:continue
       candidate={**cfg,'x':x,'y':y,'width':bw}
       try:layers=base_balloon(size,[{**blocks[0],'comic':candidate}],font,22)
       except ValueError:continue
       _,layer,(lx,ly)=layers[0];yy,xx=np.nonzero(np.asarray(layer.getchannel('A')))
       px=xx+lx;py=yy+ly
       if ref['layout']=='diagonal':
        sums=px/w+py/h
        if (sums.max()>.97 if slot==0 else sums.min()<1.04):continue
       if avoid[py,px].any():continue
       return layers,candidate
    return None
   selected=choose(arr);fallback=False
   if selected is None:
    if ref['layout']=='diagonal' or (ref['layout']=='breakout' and slot==1):raise ValueError(f'No safe position for special cut {i+1}')
    # Reserve paper space and fit the entire current framing above it.
    band=min(round(h*.48), (max(6,round(w*.025))*5+90) if blocks[0]['kind']=='dialogue' else (130 if ref['layout']=='breakout' else 100))
    art=ImageOps.contain(self.media[i],(w,h-band))
    panel=Image.new('RGBA',size,'#f7f2e8');panel.paste(art,((w-art.width)//2,0))
    self.media[i].close();self.media[i]=panel
    arr=np.zeros((h,w),dtype=bool);arr[:h-band,:]=True
    if ref['layout']=='breakout':arr[:,int(w*.69):]=True
    selected=choose(arr);fallback=True
   if selected is None:raise ValueError(f'No safe lettering for cut {i+1}')
   self.balloons[i],chosen=selected
   settings['comic']['lettering'][f'{i+1}:0']=chosen
   placement_report.append({'cut':i+1,'reserved_space':fallback,'protected_overlap_pixels':0,'placement':chosen})
  (out/'placement-check.json').write_text(json.dumps(placement_report[-32:],ensure_ascii=False,indent=2),encoding='utf8')
  self.label_font=ImageFont.truetype(font,18)
 def page(self,index,source_time,all_balloons=False):
  image=Image.fromarray(super().page(index,source_time,all_balloons));d=ImageDraw.Draw(image)
  if specs[index][0]=='double':
   # Test-only visible book gutter over the continuous image.
   for offset in range(-10,11):
    alpha=int(65*(1-abs(offset)/11));overlay=Image.new('RGBA',image.size)
    ImageDraw.Draw(overlay).line((640+offset,0,640+offset,720),fill=(40,30,20,alpha))
    image=Image.alpha_composite(image.convert('RGBA'),overlay).convert('RGB')
   d=ImageDraw.Draw(image)
  label=f'{index+1:02} / 13  {specs[index][1]}'
  width=int(d.textlength(label,font=self.label_font))+24
  d.rectangle((0,0,width,27),fill='#172529');d.text((10,3),label,font=self.label_font,fill='white')
  return np.asarray(image)
comic.ComicFrames=TestFrames
frames=TestFrames(images,durations,events,settings,(1280,720),font)
for i,page in enumerate(frames.pages):Image.fromarray(frames.page(i,page['source_end']-.001,True)).save(out/f'page_{i+1:02}.png')
manifest={'settings':settings,'pages':frames.pages,'events':events,'sources':refs,'duration':frames.duration,'reused_original_images':10,'derived_transparent_foregrounds':1,'note':'기존 이미지·음성 재편집 비교 테스트. 연속 동작은 구도 전환이며 인물 애니메이션이 아닙니다. 양면 중앙 접힘 및 방식 표시는 테스트 전용 오버레이.'}
(out/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf8')
buttons=''.join(f'<button onclick="seek({p["start"]:.3f})">{i+1:02} {specs[i][1]}</button>' for i,p in enumerate(frames.pages))
cards=''.join(f'<a href="page_{i+1:02}.png"><img loading="lazy" src="page_{i+1:02}.png"><span>{i+1:02} {s[1]}</span></a>' for i,s in enumerate(specs))
html='''<!doctype html><html lang="ko"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>낡은 검보 · 13가지 컷 테스트</title><style>body{margin:0;background:#12191c;color:#eee;font:16px system-ui}main{max-width:1280px;margin:auto;padding:24px}h1{font-size:28px}p{line-height:1.7;color:#b6c5c8}video{width:100%;background:black;border-radius:12px}nav{display:flex;flex-wrap:wrap;gap:8px;margin:20px 0}button{background:#273b40;color:#fff;border:1px solid #486267;border-radius:8px;padding:12px;cursor:pointer}button:hover{background:#43636b}.gallery{display:grid;grid-template-columns:repeat(auto-fit,minmax(340px,1fr));gap:20px}a{color:#bde3dc;text-decoration:none}img{width:100%;border-radius:8px}span{display:block;padding:8px}</style><main><h1>낡은 검보 · 3D 책장 넘김</h1><p>12가지 방식 + 격자 2×2 / 2×3 비교 · 33컷. 기존 이미지 10장과 기존 대사·음성을 재사용했습니다.<br>얼굴·검보·서찰·검의 보호 영역을 직접 지정해 자막 겹침을 피했습니다. 여백이 부족한 컷은 별도 자막 공간을 확보했습니다. 책등에 고정된 3D 종이 격자가 휘어 넘어갑니다. 뒷면은 다음 펼침의 왼쪽 그림이며, 아래에는 다음 오른쪽 그림이 보입니다.</p><video id="player" controls preload="metadata" poster="page_01.png" src="output.mp4"></video><nav>BUTTONS</nav><p>버튼으로 해당 페이지부터 재생합니다. 반복 장면은 컷 구성 비교를 위한 재편집입니다. 연속 동작은 기존 그림의 세부 구도를 순서대로 보여주는 방식이며 실제 인물 애니메이션은 아닙니다.</p><div class="gallery">CARDS</div><p><a href="output.mp4" download>영상 다운로드</a> · <a href="manifest.json">구성·원본 대응표</a></p></main><script>function seek(t){const v=document.getElementById('player');v.currentTime=t;v.play()}</script></html>'''.replace('BUTTONS',buttons).replace('CARDS',cards)
(out/'index.html').write_text(html,encoding='utf8')
print(f'PREVIEW READY: {len(refs)} cuts, {frames.duration:.2f} seconds',flush=True);frames.close()
if '--preview' not in sys.argv:
 last=[-1]
 def progress(p,t):
  if p//5!=last[0]:print(p,t,flush=True);last[0]=p//5
 print(comic.render_comic(temp_dir=str(out),images=images,durations=durations,audio_path=str(out/'speech.wav'),subtitles=events,settings=settings,resolution=(1280,720),progress_callback=progress),flush=True)
