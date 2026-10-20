'use client'
import { useEffect,useState } from 'react'
import type { MotionDraft } from '@/lib/stdMotionStudio'
export default function StdMotionAutomation({draft,onChange,onSave,disabled,busy,projectId,headers,planningOnly=false}:{draft:MotionDraft;onChange:(draft:MotionDraft)=>void;onSave:()=>void;disabled:boolean;busy:boolean;projectId:string;headers:Record<string,string>;planningOnly?:boolean}) {
    const [job,setJob]=useState<any>(null),[model,setModel]=useState(''),[error,setError]=useState('')
    useEffect(()=>{if(planningOnly)return;let cancelled=false;const load=async()=>{try{const r=await fetch(`/api/std/projects/${projectId}/motion-automation`,{headers});const d=await r.json();if(!r.ok)throw Error(d.error);if(!cancelled){setJob(d.job);setError('')}}catch(e:any){if(!cancelled)setError(e.message)}};void load();const timer=setInterval(load,15000);return()=>{cancelled=true;clearInterval(timer)}},[projectId,headers,planningOnly])
    useEffect(()=>{if(planningOnly)return;let live=true;void fetch('/api/std/video-models',{headers}).then(r=>r.json()).then(d=>{if(live)setModel(d.models?.find((m:any)=>m.id===d.active_id)?.name||'선택된 모델 없음')}).catch(()=>{if(live)setModel('모델 설정 조회 실패')});return()=>{live=false}},[headers,planningOnly])
    const automation=draft.automation||{mode:'ae_only' as const,max_ai_clips:1,max_ai_seconds:5}
    return <section className="mx-5 rounded-xl border border-cyan-400/30 bg-[#101722] p-4 text-white space-y-3">
        <h3 className="font-semibold text-cyan-200">{planningOnly?'제출 후 실행 계획 · 사전 설정':'기존 AE 제작 · Codex 자동 연출'}</h3>
        <p className="text-sm text-slate-300">원본과 최종 음성을 저장한 뒤 제출하세요. Codex가 원본·음성 구간을 확인해 연출하고, 워커가 제작·실제 출력 검수를 진행합니다. 키프레임 편집은 필요하지 않습니다.</p>
        <fieldset disabled={disabled||busy} className="space-y-3">
            <label><input type="checkbox" checked={draft.enabled&&Boolean(draft.automation)} onChange={e=>onChange({...draft,enabled:e.target.checked,automation})}/> 제출 후 자동 제작 사용</label>
            <div className="flex flex-wrap gap-4">{([['ae_only','AE 중심 자동 제작 · 영상 생성 API 미사용'],['hybrid','AI 영상 혼합 자동 제작 · 필요한 짧은 구간만 생성']] as const).map(([mode,label])=><label key={mode}><input type="radio" name={`motion-mode-${projectId}`} checked={automation.mode===mode} onChange={()=>onChange({...draft,automation:{...automation,mode}})}/> {label}</label>)}</div>
            <label>출력 비율 <select aria-label="자동 제작 출력 비율" value={draft.aspect} onChange={e=>onChange({...draft,aspect:e.target.value as MotionDraft['aspect']})} className="rounded bg-slate-800 p-2"><option value="16:9">가로 16:9</option><option value="9:16">세로 9:16</option></select></label>
            {automation.mode==='hybrid'&&<div className="space-y-2 text-sm"><p>설정에서 적용한 모델: {model} · 제출 시 고정됩니다.</p><label>AI 구간 최대 <select className="rounded bg-slate-800 p-2" value={automation.max_ai_clips} onChange={e=>onChange({...draft,automation:{...automation,max_ai_clips:Number(e.target.value)}})}>{[1,2,3].map(n=><option key={n} value={n}>{n}개</option>)}</select></label><label> 구간당 최대 <select className="rounded bg-slate-800 p-2" value={automation.max_ai_seconds} onChange={e=>onChange({...draft,automation:{...automation,max_ai_seconds:Number(e.target.value)}})}>{[3,4,5].map(n=><option key={n} value={n}>{n}초</option>)}</select></label><p className="text-xs text-slate-400">총 AI 구간은 영상 길이의 20% 이내입니다. 필요 없으면 생성하지 않으며, 결과가 원본과 다르면 검수를 통과하지 않습니다.</p></div>}
            <button type="button" onClick={onSave} className="rounded bg-cyan-700 px-3 py-2">제작 모드 저장</button>
        </fieldset>
        {job&&<div role="status" className="rounded bg-slate-900 p-3 text-sm"><p>{{queued:'워커 대기',processing:'자동 제작 중',needs_review:'보완 필요',failed:'작업 오류',complete:'출력 검수 완료'}[job.state as string]||job.state} · {job.progress||job.phase}</p><p>검수 완료 {job.reviewed_scenes||0}/{job.total_scenes||'—'}씬</p>{job.error&&<p className="text-amber-200">{job.error}</p>}{job.final_url&&<><video controls preload="metadata" src={job.final_url} className="max-h-96 w-full"/><a href={job.final_url} download>검수 완료 영상 다운로드</a></>}</div>}
        {error&&<p role="alert" className="text-amber-200">{error}</p>}
    </section>
}
