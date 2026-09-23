"""Page-level editorial layouts; opposite leaves never reuse the same source art."""
assignments=[([1,3],[2,4]),([3,1],[5,4]),([4,6],[10,5]),([5,6],[7,8]),([6,9],[7,5]),([7,4],[8,5]),([8,2],[9,1]),([9,6],[10,4]),([4,3],[10,5]),([1,2],[3,4]),([3,1],[4,10]),([10,4],[3,5]),([7,6],[5,8])]
for left,right in assignments:assert not set(left)&set(right)
faces={3:{'백운':(.58,.27),'제자':(.44,.23)},4:{'제자':(.32,.24)},5:{'백운':(.63,.30)},8:{'백운':(.55,.16)},9:{'백운':(.43,.19)},10:{'백운':(.73,.24),'제자':(.30,.51)}}

def event_for(index,side):
 event=dict(events[lines[index][side]])
 if (index,side)==(12,1):event.update(kind='thought',style='thought')
 return event

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
   event=event_for(i,side)
   # Irregular/connected dialogue is composed as one union, then outlined once.
   lettering[i,side]=make_lettering(event,variant,opacity=.88 if i in (3,7,8) else 1.)

def wrap(draw,text,font,width):
 lines=[];line=''
 for char in text:
  if line and draw.textlength(line+char,font=font)>width:lines.append(line);line=char
  else:line+=char
 if line:lines.append(line)
 return lines

def make_lettering(event,variant,target=None,opacity=1.):
 from PIL import ImageChops,ImageFilter
 layer=Image.new('RGBA',(PW,PH));mask=Image.new('L',(PW,PH));md=ImageDraw.Draw(mask)
 text=event['text'];dialogue=event['kind'] in ('dialogue','thought');thought=event['kind']=='thought';font=ImageFont.truetype(fontpath,20)
 if variant==0:box=(32,19,366,118)
 elif variant==1:box=(205,221,484,355)
 elif variant==2:box=(115,325,482,438)
 else:box=(35,21,432,132)
 x,y,r,b=box
 chunks=[text]
 if dialogue and not thought and ('…' in text or len(text)>19):
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
 if dialogue and target is not None:
  # Start at the closest lobe, trace through the union to find its true outline.
  centers=[((lx+rx)/2,(ly+by)/2) for lx,ly,rx,by in boxes]
  center=min(centers,key=lambda c:(c[0]-target[0])**2+(c[1]-target[1])**2)
  dx,dy=target[0]-center[0],target[1]-center[1];distance=math.hypot(dx,dy)
  if distance>1:
   ux,uy=dx/distance,dy/distance;root=None
   for step in range(int(distance)):
    px,py=round(center[0]+ux*step),round(center[1]+uy*step)
    if not (0<=px<PW and 0<=py<PH) or mask.getpixel((px,py))==0:
     root=(center[0]+ux*max(0,step-4),center[1]+uy*max(0,step-4));break
   if root:
    remaining=math.hypot(target[0]-root[0],target[1]-root[1])
    if thought:
     for radius,offset in ((7,16),(5,33),(3,47)):
      if offset+radius>=remaining-10:continue
      cx,cy=root[0]+ux*offset,root[1]+uy*offset
      md.ellipse((cx-radius,cy-radius,cx+radius,cy+radius),fill=255)
    elif remaining>12:
     length=min(26,remaining*.4);perp=(-uy*6,ux*6)
     md.polygon([(root[0]+perp[0],root[1]+perp[1]),(root[0]-perp[0],root[1]-perp[1]),(root[0]+ux*length,root[1]+uy*length)],fill=255)
 outline=ImageChops.subtract(mask.filter(ImageFilter.MaxFilter(5)),mask)
 layer.paste('#22242a',(0,0),outline)
 fill=Image.new('RGBA',(PW,PH),'#fffefa' if dialogue else '#f5f1e8');fill.putalpha(mask.point(lambda v:round(v*opacity)))
 layer=Image.alpha_composite(layer,fill)
 d=ImageDraw.Draw(layer)
 for chunk,(lx,ly,rx,by) in zip(chunks,boxes):
  lines=wrap(d,chunk,font,(rx-lx)*(.69 if dialogue else .9));height=len(lines)*25
  assert height<by-ly-8,(chunk,boxes)
  for k,line in enumerate(lines):d.text(((lx+rx-d.textlength(line,font=font))/2,(ly+by-height)/2+k*25),line,font=font,fill='#202128')
 return layer

def leaf(index,side,t):
 plan=plans[index,side];variant=plan['variant'];duration=pages[index]['duration'];p=max(0,min(1,t/duration));e=ease(p)
 page=Image.new('RGB',(PW,PH),'#fffefa');d=ImageDraw.Draw(page)
 event=event_for(index,side);visible_faces=[]
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
  original_h=h
  panel=crop(images[source],(w,h),z,cx,cy)
  face=faces.get(source,{}).get(event.get('speaker'))
  face_point=None
  if face:
   iw,ih=images[source].size;ch=min(ih,iw/(w/h))/z;cw=ch*w/h
   ox=max(0,min(iw-cw,cx*iw-cw/2));oy=max(0,min(ih-ch,cy*ih-ch/2))
   fx=(face[0]*iw-ox)/cw*w;fy=(face[1]*ih-oy)/ch*h
   if max(12,w*.08)<fx<w-max(12,w*.08) and max(18,h*.09)<fy<h-max(18,h*.09):face_point=(x+fx,y+fy)
  if motion=='focus':panel=Image.blend(panel.filter(ImageFilter.GaussianBlur(4)),panel,min(1,progress*2))
  # Muted cool shadows and restrained warm highlights unify the existing ink art.
  tint=Image.new('RGB',(w,h),'#46556b');panel=Image.blend(panel,tint,.065)
  if slot==1:
   q=ease(max(0,min(1,(p-.12)/.14)))
   if q<=0:continue
   ph=max(1,round(h*q));panel=panel.crop((0,0,w,ph));h=ph
   d.rectangle((x-5,y-5,x+w+5,y+h+5),fill='#fffefa')
  page.paste(panel,(x,y));d.line((x,y,x+w,y,x+w,y+h,x,y+h,x,y),fill='#202125',width=2)
  if face_point and face_point[1]<y+h-8:visible_faces.append(face_point)
  # Inset covers the underlying art; discard a hidden main-panel face.
  if slot==1:visible_faces=[f for f in visible_faces if f==face_point or not (x-5<f[0]<x+w+5 and y-5<f[1]<y+h+5)]
 # Caption footprints cross frame edges but only touch narrow edge strips, not faces.
 elapsed=t-local_starts[index][side]
 if elapsed>=0:
  bounds=lettering[index,side].getbbox();center=((bounds[0]+bounds[2])/2,(bounds[1]+bounds[3])/2)
  target=min(visible_faces,key=lambda f:(f[0]-center[0])**2+(f[1]-center[1])**2) if visible_faces else None
  layer=make_lettering(event,variant,target,opacity=.88 if index in (3,7,8) else 1.) if event['kind'] in ('dialogue','thought') else lettering[index,side]
  bounds=layer.getbbox()
  balloon=layer.crop(bounds);pos=bounds[:2]
  dialogue=event['kind']=='dialogue'
  balloon,pos=animated_balloon(balloon,pos,elapsed,dialogue)
  page.paste(balloon,pos,balloon)
 # Quiet book folio, not an effect demonstration label.
 d.text((PW//2-10,PH-24),str(index*2+side+1),font=label_font,fill='#887f77')
 return page
