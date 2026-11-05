import { wuxiaBubbleContour } from './stdWuxiaBubble'
export const wuxiaFontFamily = (font: string) => font?.startsWith('BlackHan') ? 'Black Han Sans' : font?.startsWith('DoHyeon') ? 'Do Hyeon' : 'Wuxia Noto Sans KR'
export function wuxiaTextLines(text: string, width: number, size: number) {
 const limit=Math.max(2,Math.floor(width/size)),out:string[]=[]
 for(const p of text.split('\n')) { let line=''; for(const word of p.split(/\s+/)) {
  if(line && line.length+1+word.length>limit){out.push(line);line=''}
  let rest=word;while(rest.length>limit){if(line){out.push(line);line=''}out.push(rest.slice(0,limit));rest=rest.slice(limit)}
  line+=(line?' ':'')+rest
 } if(line)out.push(line) }
 return out.length?out:['']
}
export function wuxiaGraphicPose(g:any,progress:number) {
 const s=g.style||{},p=Math.max(0,Math.min(1,progress))
 const duration=s.entry==='snap'?.06:s.entry==='impact'?.12:s.entry==='reveal'?.25:.18
 const fade=Math.min(1,p/(s.entry==='reveal'?.25:.055),(1-p)/.055)
 const settle=Math.pow(Math.max(0,1-p/duration),s.entry==='settle'?2:1),peak=(s.scale_peak||100)/100
 return {opacity:fade,scale:1+(peak-1)*settle,rotation:s.rotation||0}
}
export function wuxiaGraphicBounds(g:any) {
 const l=g.layout,s=g.style||{},a=Math.abs((s.rotation||0)*Math.PI/180),peak=Math.max(1,(s.scale_peak||100)/100)
 const w=l.size[0]*1920*peak,h=l.size[1]*1080*peak,rx=(w*Math.cos(a)+h*Math.sin(a))/2+8,ry=(w*Math.sin(a)+h*Math.cos(a))/2+8
 return [l.center[0]*1920-rx,l.center[1]*1080-ry,l.center[0]*1920+rx,l.center[1]*1080+ry]
}
export function wuxiaGraphicIsSafe(g:any,boxes:number[][]) {
 const b=wuxiaGraphicBounds(g)
 if(b[0]<12||b[1]<12||b[2]>1908||b[3]>1068)return false
 const overlaps=(a:number[],r:number[])=>a[0]<r[2]&&a[2]>r[0]&&a[1]<r[3]&&a[3]>r[1]
 if(boxes.some(r=>overlaps(b,r.map((v,i)=>v*(i%2?1080:1920)))))return false
 if(g.kind==='speech_bubble'&&!g.layout.offscreen_speaker&&g.layout.tail){
  const l=g.layout,c=[l.center[0]*1920,l.center[1]*1080],shape=wuxiaBubbleContour(c,[l.size[0]*1920,l.size[1]*1080],l.tail.map((v:number,i:number)=>v*(i?1080:1920)),g.bubble_style)
  // Check the full tail contour, not just its endpoint.
  if(shape.points.some(p=>boxes.some(r=>p[0]>=r[0]*1920-8&&p[0]<=r[2]*1920+8&&p[1]>=r[1]*1080-8&&p[1]<=r[3]*1080+8)))return false
 }
 return true
}
