'use client'
import {useEffect,useState} from 'react'
import {startVisiblePolling} from '@/lib/stdVisiblePolling'
export default function StdHorizontalWebtoon({projectId,headers,disabled}:{projectId:string;headers:Record<string,string>;disabled:boolean}) {
 const [status,setStatus]=useState<any>(null),[error,setError]=useState(''),[busy,setBusy]=useState(false)
 const endpoint=`/api/std/projects/${encodeURIComponent(projectId)}/horizontal-webtoon`
 const refresh=async(enqueue=false)=>{setError('');if(enqueue)setBusy(true);try{const r=await fetch(endpoint,{method:enqueue?'POST':'GET',headers});const data=await r.json();if(!r.ok)throw Error(data.error);setStatus(data)}catch(e:any){setError(e.message)}finally{setBusy(false)}}
 useEffect(()=>{let alive=true;const stop=startVisiblePolling(async signal=>{try{const r=await fetch(endpoint,{headers,signal});const data=await r.json();if(!r.ok)throw Error(data.error);if(alive){setStatus(data);setError('')}return data.scenes.some((s:any)=>['queued','processing'].includes(s.state))?15000:120000}catch(e:any){if(alive)setError(e.message);throw e}},15000);return()=>{alive=false;stop()}},[endpoint,JSON.stringify(headers)])
 return <div className="space-y-2 rounded border border-amber-300/30 bg-slate-900 p-3 text-sm" aria-label="가로 웹툰 컷 연출">
  <p className="font-bold text-amber-200">가로 웹툰 컷 모드 · 16:9 · AE</p>
  <p>저장된 영상은 실제 움직임을 그대로 사용합니다. 인물·배경이 분리된 PSD는 인물이나 부위 레이어의 이동·회전을 컷 연출과 함께 적용합니다. 전체 컷·클로즈업·최대 3컷 배치·순차 등장도 사용할 수 있습니다.</p>
  <p className="text-xs text-slate-400">원본과 최종 음성 → 제작 모드 저장 → 컷 연출 준비 → 준비 완료 후 제출. 일반 JPG·PNG와 합쳐진 PSD는 화면 확대만 가능합니다. 걷기 등 새로운 신체 동작을 생성하지 않습니다. 영상은 원래 속도로 재생하며 길이가 부족하면 해당 씬을 알려드립니다. 중간 정지·반복으로 늘리지 않습니다.</p>
  <button type="button" disabled={disabled||busy} onClick={()=>void refresh(true)} className="rounded bg-amber-700 px-3 py-2 disabled:opacity-40">{busy?'준비 요청 중…':'가로 웹툰 컷 연출 준비'}</button>
  {status&&<div role="status"><p>연출 준비 {status.ready}/{status.total}씬</p><ul className="max-h-48 overflow-y-auto">{status.scenes.map((s:any)=><li key={s.number}>{s.number}번 씬 · {{not_prepared:'준비 필요',queued:'대본워커 대기',processing:'원본 분석 중',ready:'연출 준비 완료',failed:'보완 필요'}[s.state as string]||s.state}{s.shots?` · ${s.shots}개 컷 전환`:''}{s.motion_capability==='existing_video'?' · 기존 영상 동작':s.motion_capability==='separated_character'?' · 분리된 인물 동작':s.motion_capability==='camera_only'?' · 화면 확대 (인물 레이어 없음)':''}{s.error&&` · ${s.error}`}</li>)}</ul></div>}
  {error&&<p role="alert" className="text-amber-200">{error}</p>}
 </div>
}
