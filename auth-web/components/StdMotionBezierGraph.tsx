'use client'
import {useRef} from 'react'
export default function StdMotionBezierGraph({value,onChange}:{value:[number,number,number,number];onChange:(v:[number,number,number,number])=>void}){
 const drag=useRef<0|2|null>(null),top=Math.min(0,1-value[1],1-value[3])-.15,bottom=Math.max(1,1-value[1],1-value[3])+.15
 const edit=(index:number,n:number)=>{const next=[...value] as typeof value;next[index]=n;if(next[0]<=next[2])onChange(next)}
 return <div className="space-y-2"><svg aria-label="베지어 보간 그래프" viewBox={`-.1 ${top} 1.2 ${bottom-top}`} className="h-52 w-full bg-slate-900" style={{touchAction:'none'}} onPointerMove={e=>{if(drag.current===null||e.currentTarget.closest('fieldset[disabled]'))return;const svg=e.currentTarget,ctm=svg.getScreenCTM();if(!ctm)return;const p=svg.createSVGPoint();p.x=e.clientX;p.y=e.clientY;const q=p.matrixTransform(ctm.inverse()),i=drag.current,next=[...value] as typeof value;next[i]=Math.max(i===0?0:value[0],Math.min(i===0?value[2]:1,q.x));next[i+1]=Math.max(-2,Math.min(3,1-q.y));onChange(next)}} onPointerUp={()=>{drag.current=null}} onPointerCancel={()=>{drag.current=null}}>
 <path d="M0 1H1 M0 1V0 M1 1V0 M0 0H1" fill="none" stroke="#475569" strokeWidth=".005"/>
 <path d={`M0 1L${value[0]} ${1-value[1]} M1 0L${value[2]} ${1-value[3]}`} stroke="#94a3b8" strokeWidth=".008"/>
 <path d={`M0 1C${value[0]} ${1-value[1]} ${value[2]} ${1-value[3]} 1 0`} fill="none" stroke="#22d3ee" strokeWidth=".015"/>
 {([0,2] as const).map(i=><circle key={i} aria-label={`베지어 핸들 ${i===0?1:2}`} cx={value[i]} cy={1-value[i+1]} r=".045" fill="#fbbf24" onPointerDown={e=>{if(e.currentTarget.closest('fieldset[disabled]'))return;drag.current=i;e.currentTarget.ownerSVGElement?.setPointerCapture(e.pointerId)}}/>)}</svg>
 <div className="flex flex-wrap gap-3">{value.map((n,i)=><label className="text-xs" key={i}>{['첫 핸들 X','첫 핸들 Y','둘째 핸들 X','둘째 핸들 Y'][i]} <input aria-label={`베지어 제어점 ${i+1}`} className="w-20 bg-slate-800" type="number" min={i%2?-2:0} max={i%2?3:1} step=".01" value={Number(n.toFixed(3))} onChange={e=>{const v=Number(e.target.value);if(Number.isFinite(v)&&v>=(i%2?-2:0)&&v<=(i%2?3:1))edit(i,v)}}/></label>)}</div><p className="text-xs">가로는 구간 시간, 세로는 진행률입니다. 핸들을 끌거나 좌표로 조절합니다.</p></div>
}
