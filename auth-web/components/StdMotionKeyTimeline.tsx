'use client'
import {useEffect,useRef,useState} from 'react'
import {sampleValue,samplePoint,type ValueKey,type PointKey,type Interpolation} from '@/lib/stdMotionRig'

type Key=ValueKey|PointKey
const modes:Record<Interpolation,string>={linear:'직선',ease:'부드럽게', 'ease-in':'천천히 시작','ease-out':'천천히 정지',hold:'정지 후 전환'}
/** A key's interpolation controls the segment leaving that key. Endpoints stay fixed. */
export default function StdMotionKeyTimeline({label,keys,onChange,time,onSeek,duration=5,fps=24,min=-360,max=360}:{label:string;keys:Key[];onChange:(keys:any[])=>void;time:number;onSeek?:(t:number)=>void;duration?:number;fps?:number;min?:number;max?:number}){
 const [selected,setSelected]=useState(0),[clipboard,setClipboard]=useState<Key|null>(null),[,refresh]=useState(0)
 const history=useRef<{past:Key[][];future:Key[][];signature:string}>({past:[],future:[],signature:JSON.stringify(keys)})
 const frames=Math.max(1,Math.round(duration*fps)),index=Math.min(selected,keys.length-1),key=keys[index],point='x' in key
 const signature=JSON.stringify(keys)
 useEffect(()=>{if(history.current.signature!==signature){history.current={past:[],future:[],signature};refresh(n=>n+1)}},[signature])
 const commit=(next:Key[])=>{const h=history.current;if(JSON.stringify(next)===signature)return;h.past=[...h.past.slice(-49),keys.map(k=>({...k}))];h.future=[];h.signature=JSON.stringify(next);onChange(next);refresh(n=>n+1)}
 const snap=(t:number)=>Math.max(0,Math.min(1,Math.round(t*frames)/frames))
 const insert=(source?:Key)=>{const t=snap(time),existing=keys.findIndex(k=>Math.abs(k.t-t)<1e-8);if(existing<0&&keys.length>=64)return;const sampled:Key=point?{t,x:samplePoint(keys as PointKey[],t)[0],y:samplePoint(keys as PointKey[],t)[1]}:{t,value:sampleValue(keys as ValueKey[],t)};const next=[...keys.filter((_,i)=>i!==existing),{...(source||sampled),t}].sort((a,b)=>a.t-b.t);commit(next);setSelected(next.findIndex(k=>k.t===t))}
 const update=(patch:Partial<Key>)=>commit(keys.map((k,i)=>i===index?{...k,...patch}:k))
 const move=(frame:number)=>{const t=snap(frame/frames);if(index===0||index===keys.length-1||t<=keys[index-1].t||t>=keys[index+1].t)return;update({t});onSeek?.(t)}
 const undo=(redo=false)=>{const h=history.current,from=redo?h.future:h.past,to=redo?h.past:h.future;if(!from.length)return;const next=from.pop()!;to.push(keys);h.signature=JSON.stringify(next);onChange(next);setSelected(0);refresh(n=>n+1)}
 return <fieldset className="my-2 space-y-2 rounded border border-slate-600 p-2"><legend>{label} 키 타임라인</legend>
  <div className="flex flex-wrap gap-2 text-xs"><button type="button" onClick={()=>insert()} disabled={keys.length>=64}>현재 프레임 키 추가</button><button type="button" onClick={()=>setClipboard({...key})}>키 복사</button><button type="button" disabled={!clipboard||keys.length>=64} onClick={()=>insert(clipboard!)}>현재 프레임에 붙여넣기</button><button type="button" disabled={index===0||index===keys.length-1} onClick={()=>{commit(keys.filter((_,i)=>i!==index));setSelected(Math.max(0,index-1))}}>선택 키 삭제</button><button type="button" disabled={!history.current.past.length} onClick={()=>undo()}>키 실행 취소</button><button type="button" disabled={!history.current.future.length} onClick={()=>undo(true)}>키 다시 실행</button></div>
  <div className="relative h-10 rounded bg-slate-900" aria-label={`${label} 키 트랙`}><div className="pointer-events-none absolute inset-y-0 w-px bg-red-400" style={{left:`${time*100}%`}}/>{keys.map((k,i)=><button type="button" key={i} aria-label={`${label} 키 ${i+1}`} aria-pressed={i===index} className={`absolute top-2 -translate-x-1/2 px-1 ${i===index?'text-cyan-300':'text-slate-300'}`} style={{left:`${2+k.t*96}%`}} onClick={()=>{setSelected(i);onSeek?.(k.t)}}>◆</button>)}</div>
  <label className="block text-xs">선택 키 프레임 <input aria-label={`${label} 키 프레임`} type="number" min={0} max={frames} step={1} value={Math.round(key.t*frames)} disabled={index===0||index===keys.length-1} onChange={e=>move(Number(e.target.value))} className="w-24 bg-slate-800"/> / {frames} ({(key.t*duration).toFixed(3)}초)</label>
  {(point?['x','y']:['value']).map(field=><label key={field} className="mr-3 inline-block text-xs">{field==='value'?'값':field.toUpperCase()} <input aria-label={`${label} 키 ${field}`} type="number" min={min} max={max} step={point?.001:1} value={(key as any)[field]} onChange={e=>{const v=Number(e.target.value);if(Number.isFinite(v)&&v>=min&&v<=max)update({[field]:v})}} className="w-24 bg-slate-800"/></label>)}
  <label className="block text-xs">다음 키까지 보간 <select aria-label={`${label} 보간`} value={key.interpolation||'linear'} disabled={index===keys.length-1} className="bg-slate-800" onChange={e=>update({interpolation:e.target.value as Interpolation})}>{Object.entries(modes).map(([v,name])=><option key={v} value={v}>{name}</option>)}</select></label>
  <p className="text-xs text-slate-400">키 추가·이동은 {fps}fps 프레임에 맞춥니다. 시작·끝 키는 유지하며, 보간은 다음 키까지 적용합니다.</p>
 </fieldset>
}
