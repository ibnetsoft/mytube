import { ComicLettering } from './stdComic'

export function balloonOutline(x:number,y:number,w:number,h:number,kind:string,style:string,tx:number,ty:number): number[][] {
    if(kind!=='dialogue') return [[x,y],[x+w,y],[x+w,y+h],[x,y+h]]
    const cx=x+w/2,cy=y+h/2,theta=Math.atan2((ty-cy)/(h/2),(tx-cx)/(w/2)),tangent=Math.hypot(w/2*Math.sin(theta),h/2*Math.cos(theta)),delta=Math.min(.12,Math.min(w,h)*.08/Math.max(tangent,1)),points:number[][]=[]
    if(((tx-cx)/(w/2))**2+((ty-cy)/(h/2))**2<=1)return Array.from({length:80},(_,i)=>{const r=style==='shout'&&i%2?.91:1;return [cx+Math.cos(Math.PI*2*i/80)*w/2*r,cy+Math.sin(Math.PI*2*i/80)*h/2*r]})
    for(let i=0;i<=80;i++) {const a=theta+delta+(Math.PI*2-2*delta)*i/80,r=style==='shout'&&i%2?.91:1;points.push([cx+Math.cos(a)*w/2*r,cy+Math.sin(a)*h/2*r])}
    const bx=cx+Math.cos(theta)*w/2,by=cy+Math.sin(theta)*h/2,dx=tx-bx,dy=ty-by,length=Math.hypot(dx,dy)
    const tailLength=Math.min(length,Math.min(w,h)*.28)
    if(length>2)points.push([bx+dx/length*tailLength,by+dy/length*tailLength])
    return points
}
export function drawLettering(ctx:CanvasRenderingContext2D,w:number,h:number,blocks:any[],fontSize:number,position:string,source:number,all:boolean,diagonal?:number) {
    const pad=Math.max(6,Math.round(w*.025));let items:any[]=[],total=0,fs=Math.floor(Math.min(fontSize,Math.max(12,w/12)))
    for(;fs>=12;fs--) {
        ctx.font=`${fs}px ComicBalloon, sans-serif`
        items=blocks.map(b=>{
            const cfg:ComicLettering=b.comic || {},kind=cfg.kind || b.dialogue_kind || 'narration',bw=Math.max(.2,Math.min(.94,cfg.width ?? .9))*w,inset=kind==='dialogue'?Math.max(pad*2,bw*.16):pad,lines:string[]=[]
            for(const paragraph of String(b.text||'').split('\n')) {let line='';for(const char of paragraph){if(line&&ctx.measureText(line+char).width>bw-inset*2){lines.push(line);line=char}else line+=char}lines.push(line)}
            const lineH=Math.ceil(fs*1.3),bh=lines.length*lineH+pad*(kind==='dialogue'?4:2)
            return {b,cfg,kind,bw,inset,lines,lineH,bh}
        })
        total=items.reduce((v,i)=>v+i.bh+pad,0)
        if(total<h*.88 || items.every(i=>i.cfg.y!=null))break
    }
    if(fs<12)throw new Error('말풍선/설명이 컷을 넘칩니다. 컷 수를 줄이거나 문구를 나눠 주세요.')
    let cursor=position==='top'?pad:h-total-pad
    for(const item of items){const {b,cfg,kind,bw,inset,lines,lineH,bh}=item,x=Math.round((cfg.x??.05)*w),y=cfg.y!=null?Math.round(cfg.y*h):cursor
        if(x<0||y<0||x+bw>w||y+bh>h)throw new Error('문구 위치가 컷 밖입니다. 위치나 폭을 조정해 주세요.')
        if(all||source>=Number(b.start_time??b.start??0)) {
            const points=balloonOutline(x,y,bw,bh,kind,cfg.style||'speech',(cfg.target_x??.5)*w,(cfg.target_y??.5)*h)
            if(diagonal!=null && points.some(([px,py])=>diagonal===0?px/w+py/h>1:px/w+py/h<1.01))throw new Error('문구가 대각선 컷 경계를 넘습니다. 위치나 폭을 조정해 주세요.')
            ctx.beginPath();points.forEach(([px,py],i)=>i?ctx.lineTo(px,py):ctx.moveTo(px,py));ctx.closePath()
            ctx.fillStyle=kind==='dialogue'?'#fffefa':'#f9f1df';ctx.strokeStyle='#252525';ctx.lineWidth=Math.max(2,Math.round(w/300));ctx.fill()
            ctx.setLineDash(kind==='dialogue'&&cfg.style==='whisper'?[6,5]:[]);ctx.stroke();ctx.setLineDash([])
            ctx.fillStyle='#171717';ctx.textBaseline='top';let ty=y+(bh-lines.length*lineH)/2
            for(const line of lines){ctx.fillText(line,kind==='dialogue'?x+(bw-ctx.measureText(line).width)/2:x+inset,ty);ty+=lineH}
        }
        cursor+=bh+pad
    }
}
