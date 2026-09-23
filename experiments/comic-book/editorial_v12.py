"""Page-level editorial layouts; opposite leaves never reuse the same source art."""
assignments=[([1,3],[2,4]),([3,1],[5,4]),([4,6],[10,5]),([5,6],[7,8]),([6,9],[7,5]),([7,4],[8,5]),([8,2],[9,1]),([9,6],[10,4]),([4,3],[10,5]),([1,2],[3,4]),([3,1],[4,10]),([10,4],[3,5]),([7,6],[5,8])]
for left,right in assignments:assert not set(left)&set(right)

def install(env):
 globals().update(env)
 global plans,lettering
 plans={};lettering={}
 patterns=[[(18,105,468,360),(285,438,195,195)],[(24,26,206,270),(18,333,468,300)],[(18,30,468,310),(35,425,285,208)],[(22,118,460,360),(30,449,190,182)]]
 for i in range(13):
  for side in range(2):
   variant=(i*2+side)%4
   motion_pair=[('in','still'),('still','up'),('left','out'),('focus','still'),('still','punch'),('down','in'),('in','right')][(i*2+side)%7]
   plans[i,side]={'variant':variant,'rects':patterns[variant],'sources':assignments[i][side],'motions':motion_pair}
   event=events[lines[i][side]]
   # Irregular/connected dialogue is composed as one union, then outlined once.
   lettering[i,side]=make_lettering(event,variant)

def wrap(draw,text,font,width):
 lines=[];line=''
 for char in text:
  if line and draw.textlength(line+char,font=font)>width:lines.append(line);line=char
  else:line+=char
 if line:lines.append(line)
 return lines

def make_lettering(event,variant):
 from PIL import ImageChops,ImageFilter
 layer=Image.new('RGBA',(PW,PH));mask=Image.new('L',(PW,PH));md=ImageDraw.Draw(mask)
 text=event['text'];dialogue=event['kind']=='dialogue';font=ImageFont.truetype(fontpath,20)
 if variant==0:box=(32,19,366,118)
 elif variant==1:box=(205,221,484,355)
 elif variant==2:box=(115,325,482,438)
 else:box=(35,21,432,132)
 x,y,r,b=box
 chunks=[text]
 if dialogue and ('…' in text or len(text)>19):
  split=text.find('…')+1 if '…' in text else max(1,len(text)//2)
  chunks=[text[:split].strip(),text[split:].strip()];chunks=[t for t in chunks if t]
 boxes=[box]
 if len(chunks)==2:
  # Two linked lobes, horizontally offset in the gutter; one continuous contour.
  mid=x+(r-x)*.51
  boxes=[(x,y,int(mid+22),b-22),(int(mid-22),y+23,r,b+12)]
 for j,(lx,ly,rx,by) in enumerate(boxes):
  if not dialogue:md.rounded_rectangle((lx,ly,rx,by),radius=3,fill=255)
  elif event.get('style')=='shout':
   md.polygon([(lx+15,ly),(rx-18,ly+3),(rx,ly+24),(rx-4,by-19),(rx-27,by),(lx+20,by-3),(lx,by-23),(lx+3,ly+24)],fill=255)
  else:md.ellipse((lx,ly,rx,by),fill=255)
 if dialogue:
  lx,ly,rx,by=boxes[-1]
  md.polygon([(rx-58,by-11),(rx-32,by-9),(rx-21,by+16)],fill=255)
 outline=ImageChops.subtract(mask.filter(ImageFilter.MaxFilter(5)),mask)
 layer.paste('#22242a',(0,0),outline);layer.paste('#fffefa' if dialogue else '#f5f1e8',(0,0),mask)
 d=ImageDraw.Draw(layer)
 for chunk,(lx,ly,rx,by) in zip(chunks,boxes):
  lines=wrap(d,chunk,font,(rx-lx)*(.69 if dialogue else .9));height=len(lines)*25
  assert height<by-ly-8,(chunk,boxes)
  for k,line in enumerate(lines):d.text(((lx+rx-d.textlength(line,font=font))/2,(ly+by-height)/2+k*25),line,font=font,fill='#202128')
 return layer

def leaf(index,side,t):
 plan=plans[index,side];variant=plan['variant'];duration=pages[index]['duration'];p=max(0,min(1,t/duration));e=ease(p)
 page=Image.new('RGB',(PW,PH),'#fffefa');d=ImageDraw.Draw(page)
 for slot,((x,y,w,h),source,motion) in enumerate(zip(plan['rects'],plan['sources'],plan['motions'])):
  # Separate timing and different motion per cut. The reaction inset arrives later.
  progress=ease(max(0,min(1,(p-slot*.18)/(1-slot*.18))))
  z=1;cx=.5;cy=.38 if source in (3,4,5,8,10) else .55
  if motion=='in':z=1+.13*progress
  elif motion=='out':z=1.16-.16*progress
  elif motion=='left':z=1.16;cx=.58-.16*progress
  elif motion=='right':z=1.16;cx=.42+.16*progress
  elif motion=='up':cy=.58-.23*progress
  elif motion=='down':cy=.3+.23*progress
  elif motion=='punch':z=1+.2*ease(min(1,max(0,(p-.2)/.12)))
  panel=crop(images[source],(w,h),z,cx,cy)
  if motion=='focus':panel=Image.blend(panel.filter(ImageFilter.GaussianBlur(4)),panel,min(1,progress*2))
  # Muted cool shadows and restrained warm highlights unify the existing ink art.
  tint=Image.new('RGB',(w,h),'#46556b');panel=Image.blend(panel,tint,.065)
  if slot==1:
   q=ease(max(0,min(1,(p-.12)/.14)))
   if q<=0:continue
   ph=max(1,round(h*q));panel=panel.crop((0,0,w,ph));h=ph
   d.rectangle((x-5,y-5,x+w+5,y+h+5),fill='#fffefa')
  page.paste(panel,(x,y));d.line((x,y,x+w,y,x+w,y+h,x,y+h,x,y),fill='#202125',width=2)
 # Caption footprints cross frame edges but only touch narrow edge strips, not faces.
 elapsed=t-local_starts[index][side]
 if elapsed>=0:
  layer=lettering[index,side];bounds=layer.getbbox()
  balloon=layer.crop(bounds);pos=bounds[:2]
  dialogue=events[lines[index][side]]['kind']=='dialogue'
  balloon,pos=animated_balloon(balloon,pos,elapsed,dialogue)
  page.paste(balloon,pos,balloon)
 # Quiet book folio, not an effect demonstration label.
 d.text((PW//2-10,PH-24),str(index*2+side+1),font=label_font,fill='#887f77')
 return page
