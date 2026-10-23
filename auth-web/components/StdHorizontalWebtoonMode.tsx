'use client'
import {useEffect,useState} from 'react'
import {motionForProject,normalizeMotionDraft,switchMotionProduction} from '@/lib/stdMotionStudio'
import StdHorizontalWebtoon from './StdHorizontalWebtoon'
export default function StdHorizontalWebtoonMode({project,headers,onSaved}:{project:any;headers:Record<string,string>;onSaved:()=>Promise<unknown>}) {
 const saved=project.project_payload?.render_settings?.motion
 const [mode,setMode]=useState(saved?.edit_mode||'standard'),[busy,setBusy]=useState(false),[error,setError]=useState('')
 useEffect(()=>{setMode(saved?.edit_mode||'standard');setError('')},[project.id,JSON.stringify(saved)])
 const disabled=Boolean(project.submitted_at)||['approved','canceled'].includes(project.status)
 const save=async()=>{setBusy(true);setError('');try{
  const previous=motionForProject(project)||{version:1 as const,enabled:false,aspect:'16:9' as const,fps:24 as const,scenes:{}}
  const base=mode==='horizontal_webtoon'?switchMotionProduction(previous,'ae'):previous
  const motion=normalizeMotionDraft({...base,edit_mode:mode==='horizontal_webtoon'?'horizontal_webtoon':undefined,...(mode==='horizontal_webtoon'?{enabled:true,production_method:'ae',aspect:'16:9',automation:{mode:'ae_only',max_ai_clips:1,max_ai_seconds:5}}:{})})
  const response=await fetch(`/api/std/projects/${project.id}`,{method:'PATCH',headers:{...headers,'Content-Type':'application/json'},body:JSON.stringify({project_payload:{render_settings:{...project.project_payload?.render_settings,motion}}})})
  const data=await response.json();if(!response.ok)throw Error(data.error||'제작 모드 저장 실패');await onSaved()
 }catch(e:any){setError(e.message)}finally{setBusy(false)}}
 return <section className="mb-3 rounded-xl border border-cyan-400/30 bg-[#101722] p-3 text-xs" aria-label="웹툰 자동 제작 모드">
  <div className="flex flex-wrap items-center gap-3"><label>제작 모드 <select aria-label="웹툰 자동 제작 모드" disabled={disabled||busy} value={mode} onChange={e=>setMode(e.target.value)} className="rounded bg-slate-800 p-2"><option value="standard">기존 제작 모드</option><option value="horizontal_webtoon">가로 웹툰 컷 모드 · AE · 16:9</option></select></label><button type="button" disabled={disabled||busy} onClick={()=>void save()} className="rounded bg-cyan-700 px-3 py-2 disabled:opacity-40">{busy?'저장 중…':'제작 모드 저장'}</button></div>
  {mode!== (saved?.edit_mode||'standard')&&<p className="mt-2 text-amber-200">제작 모드를 저장한 뒤 연출을 준비해 주세요.</p>}
  {saved?.edit_mode==='horizontal_webtoon'&&<div className="mt-3"><StdHorizontalWebtoon projectId={project.id} headers={headers} disabled={disabled||busy}/></div>}
  {error&&<p role="alert" className="mt-2 text-amber-200">{error}</p>}
 </section>
}
