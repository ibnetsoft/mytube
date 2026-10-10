"""Semantic captions and continuous-outline speech balloons."""
import math
from PIL import Image, ImageDraw, ImageFont

def outline(x,y,w,h,kind,style,target):
    if kind!='dialogue':return [(x,y),(x+w,y),(x+w,y+h),(x,y+h)]
    cx,cy=x+w/2,y+h/2
    tx,ty=target
    if ((tx-cx)/(w/2))**2+((ty-cy)/(h/2))**2 <= 1:
        return [(cx+math.cos(math.tau*i/80)*w/2*(.91 if style=='shout' and i%2 else 1),
                 cy+math.sin(math.tau*i/80)*h/2*(.91 if style=='shout' and i%2 else 1)) for i in range(80)]
    theta=math.atan2((ty-cy)/(h/2),(tx-cx)/(w/2))
    # The ellipse arc at the tail root is omitted; one closed boundary is stroked.
    tangent=math.hypot(w/2*math.sin(theta),h/2*math.cos(theta))
    delta=min(.12,min(w,h)*.08/max(tangent,1));points=[]
    for i in range(81):
        a=theta+delta+(math.tau-2*delta)*i/80
        radius=.91 if style=='shout' and i%2 else 1
        points.append((cx+math.cos(a)*w/2*radius,cy+math.sin(a)*h/2*radius))
    bx,by=cx+math.cos(theta)*w/2,cy+math.sin(theta)*h/2
    dx,dy=tx-bx,ty-by;length=math.hypot(dx,dy)
    tail_length=min(length,min(w,h)*.28)
    if length>2:points.append((bx+dx/length*tail_length,by+dy/length*tail_length))
    return points

def caption_layers(size,blocks,font_path,font_size,position='bottom'):
    if not blocks:return []
    w,h=size;pad=max(6,round(w*.025));result=[]
    for fs in range(int(max(12,min(font_size,max(12,w/12)))),11,-1):
        font=ImageFont.truetype(font_path,fs);measure=ImageDraw.Draw(Image.new('RGB',size));items=[]
        for b in blocks:
            cfg=b.get('comic') or {}
            kind=cfg.get('kind') or b.get('dialogue_kind') or 'narration'
            width=max(.2,min(.94,float(cfg.get('width',.9))))*w
            inset=max(pad*2,width*.16) if kind=='dialogue' else pad
            lines=[]
            for paragraph in str(b.get('text','')).split('\n'):
                line=''
                for char in paragraph:
                    if line and measure.textlength(line+char,font=font)>width-inset*2:lines.append(line);line=char
                    else:line+=char
                lines.append(line)
            line_h=math.ceil(fs*1.3);bh=len(lines)*line_h+pad*(4 if kind=='dialogue' else 2)
            items.append((b,cfg,kind,width,lines,line_h,bh,inset))
        total=sum(i[6]+pad for i in items)
        if total<h*.88 or all('y' in i[1] for i in items):break
    else:raise ValueError('말풍선/설명이 컷을 넘칩니다. 컷 수를 줄이거나 문구를 나눠 주세요.')
    cursor=pad if position=='top' else h-total-pad
    for b,cfg,kind,bw,lines,line_h,bh,inset in items:
        x=round(float(cfg.get('x',.05))*w);y=round(float(cfg['y'])*h) if 'y' in cfg else cursor
        if x<0 or y<0 or x+bw>w or y+bh>h:raise ValueError('문구 위치가 컷 밖입니다. 위치나 폭을 조정해 주세요.')
        style=cfg.get('style','speech');target=(float(cfg.get('target_x',.5))*w,float(cfg.get('target_y',.5))*h)
        layer=Image.new('RGBA',size);d=ImageDraw.Draw(layer)
        points=outline(x,y,bw,bh,kind,style,target)
        d.polygon(points,fill='#fffefa' if kind=='dialogue' else '#f9f1df')
        if style=='whisper' and kind=='dialogue':
            for i in range(0,len(points)-1,2):d.line(points[i:i+2],fill='#555',width=2)
        else:d.line(points+[points[0]],fill='#252525',width=max(2,round(w/300)),joint='curve')
        ty=y+(bh-len(lines)*line_h)/2
        for line in lines:
            tx=x+inset if kind!='dialogue' else x+(bw-d.textlength(line,font=font))/2
            d.text((tx,ty),line,font=font,fill='#171717',anchor='lt');ty+=line_h
        bounds=layer.getbbox();result.append((float(b.get('start',b.get('start_time',0))),layer.crop(bounds),bounds[:2]))
        cursor+=bh+pad
    return result
