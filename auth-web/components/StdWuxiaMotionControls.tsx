'use client'
import {useState} from 'react'
import {joinWuxiaMotion,splitWuxiaMotion,WUXIA_PANS,WUXIA_ZOOMS} from '@/lib/stdWuxiaMotion'
export default function StdWuxiaMotionControls({value,busy,onSave}:{value:string;busy:boolean;onSave:(value:string)=>void}){
 const initial=splitWuxiaMotion(value),[pan,setPan]=useState<string>(initial.pan),[zoom,setZoom]=useState<string>(initial.zoom),[heat,setHeat]=useState(initial.heat)
 return <div className="space-y-4 text-sm text-white">
  <label className="block">이동 방향<select aria-label="무협 이동 방향" value={pan} onChange={e=>setPan(e.target.value)} disabled={busy} className="ml-3 rounded bg-slate-800 p-2">{WUXIA_PANS.map(p=><option key={p.id} value={p.id}>{p.label}</option>)}</select></label>
  <label className="block">확대·축소<select aria-label="무협 줌 방향" value={zoom} onChange={e=>setZoom(e.target.value)} disabled={busy} className="ml-3 rounded bg-slate-800 p-2">{WUXIA_ZOOMS.map(z=><option key={z.id} value={z.id}>{z.label}</option>)}</select></label>
  <label className="flex items-center gap-2"><input aria-label="열기 아지랑이 왜곡" type="checkbox" checked={heat} onChange={e=>setHeat(e.target.checked)} disabled={busy}/>불길·열기 아지랑이 왜곡</label>
  <p className="text-xs text-slate-400">씬 시작에 짧게 이동·확대·축소한 뒤 구도를 유지합니다. 열기 왜곡은 얼굴 보호 영역과 말풍선·글자를 유지합니다.</p>
  <button type="button" disabled={busy} onClick={()=>onSave(joinWuxiaMotion(pan,zoom,heat))} className="rounded bg-cyan-700 px-4 py-2 disabled:opacity-40">선택한 씬에 모션 적용</button>
 </div>
}
