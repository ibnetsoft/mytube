"""Local prototype: semantic lettering with per-line placement and speaker targets."""
import math
from PIL import Image, ImageDraw, ImageFont

def wrap(draw, text, font, width):
    lines=[]
    for paragraph in text.split('\n'):
        line=''
        for word in paragraph.split(' '):
            candidate=(line+' '+word).strip()
            if draw.textlength(candidate,font=font)<=width:
                line=candidate
            else:
                if line: lines.append(line)
                line=''
                for char in word:
                    if line and draw.textlength(line+char,font=font)>width:
                        lines.append(line);line=''
                    line+=char
        if line:lines.append(line)
    return lines

def lettering(size,blocks,font_path,font_size,position='bottom'):
    w,h=size
    result=[]
    for block in blocks:
        kind=block['kind'];style=block.get('style','speech')
        place=block['placement'];x,y,bw=[round(v*k) for v,k in zip(place,(w,h,w))]
        font=ImageFont.truetype(font_path,round((23 if kind=='narration' else 25)*w/595))
        measure=ImageDraw.Draw(Image.new('RGB',size))
        inset=16 if kind=='narration' else 30
        inner=bw-inset*2
        lines=wrap(measure,block['text'],font,inner)
        line_h=round(font.size*1.35)
        bh=len(lines)*line_h+(26 if kind=='narration' else 46)
        if x<0 or y<0 or x+bw>w or y+bh>h:
            raise ValueError(f'Lettering overflow: {block["text"]}')
        block['render_bounds']=[x,y,x+bw,y+bh]
        for face in block.get('avoid_faces',[]):
            fx,fy,fw,fh=[v*k for v,k in zip(face,(w,h,w,h))]
            if x<fx+fw and x+bw>fx and y<fy+fh and y+bh>fy:
                raise ValueError(f'Lettering obscures face: {block["text"]}')
        layer=Image.new('RGBA',size);d=ImageDraw.Draw(layer)
        if kind=='narration':
            d.rectangle((x+3,y+3,x+bw+3,y+bh+3),fill=(0,0,0,100))
            d.rectangle((x,y,x+bw,y+bh),fill='#f9f1df',outline='#252525',width=2)
        else:
            tx,ty=[v*k for v,k in zip(block['target'],(w,h))]
            cx,cy=x+bw/2,y+bh/2;dx,dy=tx-cx,ty-cy
            length=math.hypot(dx,dy)
            ux,uy=dx/max(1,length),dy/max(1,length)
            scale=1/math.sqrt((ux/(bw/2))**2+(uy/(bh/2))**2)
            bx,by=cx+ux*scale*.82,cy+uy*scale*.82
            reach=min(100,max(8,math.hypot(tx-bx,ty-by)-9))
            tip=(bx+ux*reach,by+uy*reach)
            d.polygon([(bx-uy*10,by+ux*10),tip,(bx+uy*10,by-ux*10)],fill='white',outline='#242424',width=2)
            if style=='shout':
                points=[]
                for i in range(48):
                    angle=i*math.tau/48;r=1 if i%2==0 else .91
                    points.append((cx+math.cos(angle)*bw/2*r,cy+math.sin(angle)*bh/2*r))
                d.polygon(points,fill='white',outline='#222',width=3)
            elif style=='whisper':
                d.ellipse((x,y,x+bw,y+bh),fill='#fffefa')
                for start in range(0,360,16):d.arc((x,y,x+bw,y+bh),start,start+9,fill='#666',width=2)
            else:
                d.ellipse((x,y,x+bw,y+bh),fill='white',outline='#242424',width=2)
        ty=y+(bh-len(lines)*line_h)/2
        for line in lines:
            tx=x+inset if kind=='narration' else x+(bw-d.textlength(line,font=font))/2
            d.text((tx,ty),line,font=font,fill='#181818',anchor='lt');ty+=line_h
        bounds=layer.getbbox()
        result.append((float(block['start']),layer.crop(bounds),bounds[:2]))
    return result

def book_turn(previous,following,progress):
    """A leaf rotates around the book spine; its reverse carries the next left page."""
    import numpy as np
    if progress<=0:return previous.copy()
    if progress>=1:return following.copy()
    h,w=previous.shape[:2];hinge=w//2
    p=progress*progress*(3-2*progress);angle=p*math.pi
    extent=round(hinge*math.cos(angle));lift=math.sin(angle)
    canvas=previous.copy();canvas[:,hinge:]=following[:,hinge:]
    # Shadow cast by the lifted leaf on the underlying spread.
    xx=np.arange(w)
    shadow=np.exp(-np.abs(xx-hinge)/max(2,70*lift))*.30*lift
    canvas=(canvas*(1-shadow)[None,:,None]).astype(np.uint8)
    if abs(extent)>1:
        xs=np.arange(min(hinge,hinge+extent),max(hinge,hinge+extent))
        u=np.clip((xs-hinge)/extent,0,1)
        inset=(36*lift*np.sin(u*math.pi/2)).astype(int)
        source=previous[:,hinge:] if extent>0 else following[:,:hinge]
        tx=np.clip((u if extent>0 else 1-u)*(hinge-1),0,hinge-1).astype(int)
        ys=np.arange(h)[:,None]
        sy=np.clip(((ys-inset[None,:])/(h-2*inset)[None,:]*(h-1)),0,h-1).astype(int)
        pixels=source[sy,tx[None,:]].astype(float)
        shade=(1-.18*lift+.10*lift*np.sin(u*math.pi))[None,:,None]
        pixels=np.clip(pixels*shade,0,255).astype(np.uint8)
        valid=(ys>=inset[None,:])&(ys<h-inset[None,:])
        canvas[:,xs]=np.where(valid[:,:,None],pixels,canvas[:,xs])
        edge=hinge+extent
        if 0<=edge<w:canvas[inset[-1]:h-inset[-1],edge]=[225,217,195]
    canvas[:,hinge-1:hinge+1]=(canvas[:,hinge-1:hinge+1]*.78).astype(np.uint8)
    return canvas
