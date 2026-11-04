/** Unified closed contour; no internal body/tail stroke. Pixel coordinates. */
export function wuxiaBubbleContour(c: number[], s: number[], t?: number[]) {
 const [x,y]=c, [w,h]=s, rx=w/2, ry=h/2, dx=(t?.[0]??x)-x, dy=(t?.[1]??y)-y
 const a=Math.atan2(dy/ry,dx/rx), root=[x+rx*Math.cos(a),y+ry*Math.sin(a)]
 const vx=(t?.[0]??root[0])-root[0], vy=(t?.[1]??root[1])-root[1], d=Math.hypot(vx,vy)
 const length=Math.min(54,Math.max(0,d-64)), tail=!!t&&length>2&&Math.hypot(dx/rx,dy/ry)>1
 const half=Math.min(.14,18/Math.max(1,Math.hypot(rx*Math.sin(a),ry*Math.cos(a))))
 const points:number[][]=[]
 for(let i=0;i<=160;i++){const q=a+(tail?half:0)+(Math.PI*2-(tail?half*2:0))*i/160;points.push([x+rx*Math.cos(q),y+ry*Math.sin(q)])}
 const tip=tail?[root[0]+vx/d*length,root[1]+vy/d*length]:null
 if(tip)points.push(tip)
 return {points,tip,tailLength:tail?length:0,path:`M ${points.map(p=>p.join(' ')).join(' L ')} Z`}
}
