/** Unified closed contour; no internal body/tail stroke. Pixel coordinates. */
export function wuxiaBubbleContour(c: number[], s: number[], t?: number[], style = 'dialogue') {
 const [x,y]=c, [w,h]=s, rx=w/2, ry=h/2, dx=(t?.[0]??x)-x, dy=(t?.[1]??y)-y
 const a=Math.atan2(dy/ry,dx/rx), root=[x+rx*Math.cos(a),y+ry*Math.sin(a)]
 const vx=(t?.[0]??root[0])-root[0], vy=(t?.[1]??root[1])-root[1], d=Math.hypot(vx,vy)
 if (style==='thought'||style==='narration')t=undefined
 const length=Math.min(54,Math.max(0,d-64)), tail=!!t&&length>2&&Math.hypot(dx/rx,dy/ry)>1
 const half=Math.min(.14,18/Math.max(1,Math.hypot(rx*Math.sin(a),ry*Math.cos(a))))
 const points:number[][]=[]
 const point=(q:number)=>{
  const co=Math.cos(q),si=Math.sin(q)
  if(style==='rounded'||style==='narration'||style==='electronic'){
   const power=style==='rounded'?.45:style==='electronic'?.3:.05
   return [x+rx*Math.sign(co)*Math.pow(Math.abs(co),power),y+ry*Math.sign(si)*Math.pow(Math.abs(si),power)]
  }
  const radius=style==='thought'? .94+.06*Math.cos(q*10) : 1
  return [x+rx*co*radius,y+ry*si*radius]
 }
 const steps=style==='shout'?40:style==='reaction'?24:160
 for(let i=0;i<=steps;i++){const q=a+(tail?half:0)+(Math.PI*2-(tail?half*2:0))*i/steps;const p=point(q);if((style==='shout'||style==='reaction')&&i%2){p[0]=x+(p[0]-x)*.86;p[1]=y+(p[1]-y)*.86}points.push(p)}
 const tip=tail?[root[0]+vx/d*length,root[1]+vy/d*length]:null
 if(tip)points.push(tip)
 return {points,tip,tailLength:tail?length:0,path:`M ${points.map(p=>p.join(' ')).join(' L ')} Z`}
}
