'use client'
import {useEffect,useRef} from 'react'
import {cinematicMask} from '@/lib/stdWuxiaCinematic'
export default function StdWuxiaCinematic({frame}:{frame:any}){
 const ref=useRef<HTMLCanvasElement>(null),mask=JSON.stringify(frame.descriptor.mask)
 useEffect(()=>{if(!frame.descriptor.mask||!ref.current)return;const c=ref.current.getContext('2d');if(c)c.putImageData(new ImageData(cinematicMask(JSON.parse(mask)),960,540),0,0)},[mask])
 const p=frame.descriptor.panel,box=p?.rect,cx=box?(box[0]+box[2])*960:0,cy=box?(box[1]+box[3])*540:0
 return <>
 {frame.descriptor.mask&&<canvas ref={ref} width={960} height={540} className="absolute inset-0 w-full h-full" data-wuxia-vignette style={{opacity:frame.vignette_opacity}}/>}
 {p&&<svg className="absolute inset-0 w-full h-full" viewBox="0 0 1920 1080" data-wuxia-info-panel data-panel-scale={frame.panel_scale} data-panel-opacity={frame.panel_opacity}>
 <g opacity={frame.panel_opacity} transform={`translate(${cx} ${cy}) scale(${frame.panel_scale}) translate(${-cx} ${-cy})`}>
 <rect x={box[0]*1920} y={box[1]*1080} width={(box[2]-box[0])*1920} height={(box[3]-box[1])*1080} rx={12} fill="#101c2b" fillOpacity={.76} stroke="#d7ba73" strokeWidth={2}/>
 <text x={cx} y={cy-(p.lines.length-1)*p.font_size*.65} textAnchor="middle" dominantBaseline="central" fontFamily="Wuxia Noto Sans KR" fontWeight="bold" fontSize={p.font_size} fill="#fff2ca">{p.lines.map((line:string,i:number)=><tspan key={i} x={cx} dy={i?p.font_size*1.3:0}>{line}</tspan>)}</text>
 </g></svg>}
 </>
}
