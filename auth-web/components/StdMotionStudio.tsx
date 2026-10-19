'use client'

import { useEffect, useRef, useState } from 'react'
import StdMotionAutomation from './StdMotionAutomation'
import { AE_SCENE_EFFECTS } from '../lib/stdAeSceneEffects'
import { interpolateMotion, MotionDraft, MotionKey, motionKey, motionPreset, motionScene, MOTION_PRESETS, normalizeMotionDraft } from '../lib/stdMotionStudio'

export default function StdMotionStudio({ value, scenes, disabled, onSave, onUpload, projectId, headers, renderHistory=[], defaultAspect='16:9' }: {
    value: any; scenes: any[]; disabled: boolean; onSave: (draft: MotionDraft) => Promise<void>; onUpload: (scene: any, file: File) => Promise<unknown>; projectId: string; headers: Record<string,string>; renderHistory?:any[]; defaultAspect?:MotionDraft['aspect']
}) {
    const [draft,setDraft]=useState<MotionDraft>(()=>value ? normalizeMotionDraft(value) : {version:1,enabled:false,aspect:defaultAspect,fps:24,scenes:{}})
    const [index,setIndex]=useState(0), [time,setTime]=useState(0), [playing,setPlaying]=useState(false), [busy,setBusy]=useState(false), [error,setError]=useState(''), [notice,setNotice]=useState('')
    const [jobs,setJobs]=useState<any[]>([]), [open,setOpen]=useState(false)
    const [preparations,setPreparations]=useState<any[]>([])
    const canvas=useRef<HTMLCanvasElement>(null), video=useRef<HTMLVideoElement>(null), image=useRef<HTMLImageElement>(null)
    const selected=scenes[index], number=Number(selected?.scene_number || index+1), scene=draft.scenes[String(number)] || motionScene()
    const source=scene.source==='image' ? selected?.image_url : scene.source==='video' ? selected?.video_url : selected?.video_url || selected?.image_url
    const isVideo=scene.source==='video' || (scene.source!=='image' && Boolean(selected?.video_url))
    const update=(changes: Partial<typeof scene>)=>setDraft(d=>({...d,scenes:{...d.scenes,[number]:{...scene,...changes}}}))
    const serialized=JSON.stringify(value)
    useEffect(()=>{ if(serialized) setDraft(normalizeMotionDraft(JSON.parse(serialized))) },[serialized]) // saved server snapshot
    useEffect(()=>{setTime(0);setPlaying(false)},[index])
    useEffect(()=>{
        if(!playing)return
        let frame=0, previous=performance.now()
        const tick=(now:number)=>{const delta=(now-previous)/5000;previous=now;setTime(t=>{if(t+delta>=1){setPlaying(false);return 1}return t+delta});frame=requestAnimationFrame(tick)}
        frame=requestAnimationFrame(tick);return()=>cancelAnimationFrame(frame)
    },[playing])
    useEffect(()=>{
        const media=video.current
        if(media && Number.isFinite(media.duration) && media.duration>0) media.currentTime=Math.min(time*media.duration,media.duration-.001)
    },[time])
    const draw=()=>{
        const c=canvas.current;if(!c)return
        c.width=draft.aspect==='9:16'?360:640;c.height=draft.aspect==='9:16'?640:360
        const ctx=c.getContext('2d')!;ctx.fillStyle='#0c1018';ctx.fillRect(0,0,c.width,c.height)
        const media=isVideo?video.current:image.current
        const w=isVideo?video.current?.videoWidth:image.current?.naturalWidth,h=isVideo?video.current?.videoHeight:image.current?.naturalHeight
        if(media && w && h){const p=interpolateMotion(scene.keys,time), fit=scene.fit==='cover'?Math.max(c.width/w,c.height/h):Math.min(c.width/w,c.height/h)
            ctx.save();ctx.translate(c.width/2,c.height/2);ctx.rotate(p.rotation*Math.PI/180);ctx.scale(p.scale,p.scale);ctx.globalAlpha=p.opacity/100
            ctx.drawImage(media,-w*fit*p.x,-h*fit*p.y,w*fit,h*fit);ctx.restore()}
        ctx.save();ctx.setLineDash([5,4]);ctx.strokeStyle='#22d3eeaa';ctx.strokeRect(c.width*.08,c.height*.1,c.width*.84,c.height*.72);ctx.restore()
        ctx.fillStyle='#22d3ee';ctx.font='11px sans-serif';ctx.fillText('자막·주요 피사체 안전 영역',c.width*.08,c.height*.1-6)
    }
    useEffect(()=>{draw()},[draft,time,index,source,open])
    const save=async()=>{setBusy(true);setError('');try{await onSave(normalizeMotionDraft(draft));setNotice('Motion Studio 설정 저장 완료')}catch(e:any){setError(e.message)}finally{setBusy(false)}}
    const previews=async(action:'read'|'preview'|'direction')=>{setError('');setBusy(true);try{if(action!=='read')await onSave(normalizeMotionDraft(draft));const response=await fetch(`/api/std/projects/${projectId}/motion`,{method:action==='read'?'GET':'POST',headers:{...headers,'Content-Type':'application/json'},...(action!=='read'?{body:JSON.stringify({scene_number:number,action})}:{})});const data=await response.json();if(!response.ok)throw new Error(data.error);setJobs(data.jobs||[]);setPreparations(data.preparations||[]);if(action!=='read')setNotice('워커 작업 요청 완료. 처리 후 상태를 새로고침해 주세요.')}catch(e:any){setError(e.message)}finally{setBusy(false)}}
    const keyField=(k:MotionKey,field:keyof MotionKey,label:string,min:number,max:number,step:number)=> <label key={field} className="text-xs">{label}<input aria-label={`${Math.round(k.t*100)}% ${label}`} type="number" value={k[field]} min={min} max={max} step={step} disabled={disabled||busy} onChange={e=>update({keys:scene.keys.map(item=>item===k?{...k,[field]:Number(e.target.value)}:item)})} className="ml-1 w-20 rounded bg-slate-800 p-1"/></label>
    return <><StdMotionAutomation draft={draft} onChange={setDraft} onSave={()=>void save()} disabled={disabled} busy={busy} projectId={projectId} headers={headers}/>
        {notice&&<p role="status" className="mx-5 text-xs text-cyan-200">{notice}</p>}{error&&<p role="alert" className="mx-5 text-sm text-red-300">{error}</p>}
        <details className="mx-5 rounded-xl border border-cyan-400/30 bg-[#101722] p-4 text-white" onToggle={e=>setOpen(e.currentTarget.open)}>
        <summary className="cursor-pointer font-semibold text-cyan-200">고급 수동 연출 · 선택 사항</summary>
        {open&&<div className="mt-4 space-y-4">
            <div className="flex flex-wrap items-center gap-4 text-sm">
                <label><input type="checkbox" disabled={disabled||busy} checked={draft.enabled} onChange={e=>setDraft({...draft,enabled:e.target.checked})}/> Motion Studio 사용</label>
                <label>출력 비율 <select aria-label="Motion 출력 비율" disabled={disabled||busy} value={draft.aspect} onChange={e=>setDraft({...draft,aspect:e.target.value as MotionDraft['aspect']})} className="rounded bg-slate-800 p-2"><option value="16:9">가로 16:9 · 유튜브</option><option value="9:16">세로 9:16 · Shorts</option></select></label>
                <label>FPS <select disabled={disabled||busy} value={draft.fps} onChange={e=>setDraft({...draft,fps:Number(e.target.value) as 24|30})} className="rounded bg-slate-800 p-2"><option>24</option><option>30</option></select></label>
                <button type="button" disabled={disabled||busy} onClick={()=>void save()} className="rounded bg-cyan-700 px-3 py-2 disabled:opacity-40">설정·타임라인 저장</button>
            </div>
            <p className="text-xs text-slate-400">이미지·영상은 자체 모션 렌더, PSD 레이어는 PSD 장면 연출 화면에서 검수합니다. 컷 길이는 확정 음성에 맞춰집니다. 캔버스는 구도·키프레임 초안이며 효과는 워커 MP4로 확인하세요.</p>
            <div className="flex gap-2 overflow-auto pb-2" aria-label="Motion 씬 타임라인">{scenes.map((s,i)=><button type="button" key={s.id||s.scene_number} aria-pressed={index===i} onClick={()=>setIndex(i)} className={`shrink-0 rounded border px-3 py-2 text-xs ${index===i?'border-cyan-300 bg-cyan-900':'border-white/15'}`}>씬 {s.scene_number} · {s.scene_title||'장면'}</button>)}</div>
            {selected&&<>
                <div className="grid gap-4 lg:grid-cols-2">
                    <div className="flex items-center justify-center rounded bg-black/40 p-3"><canvas ref={canvas} aria-label="Motion 구도 미리보기" className="max-h-[480px] max-w-full"/></div>
                    <div className="space-y-3">
                        <label className="block text-xs">씬 소스 <select value={scene.source} disabled={disabled||busy} onChange={e=>update({source:e.target.value as typeof scene.source,layers:undefined})} className="ml-2 rounded bg-slate-800 p-2"><option value="auto">영상 우선 자동</option><option value="image">이미지</option><option value="video">기존 영상</option><option value="psd">검수된 PSD / AE</option></select></label>
                        <label className="block text-xs">화면 맞춤 <select value={scene.fit} disabled={disabled||busy} onChange={e=>update({fit:e.target.value as 'cover'|'contain'})} className="ml-2 rounded bg-slate-800 p-2"><option value="contain">원본 전체 보존</option><option value="cover">화면 채우기</option></select></label>
                        <label className="block text-xs">이미지·영상 업로드<input type="file" accept="image/png,image/jpeg,image/webp,video/mp4,video/webm,video/quicktime" disabled={disabled||busy} className="mt-2 block text-xs" onChange={async e=>{const file=e.target.files?.[0];e.target.value='';if(!file)return;setBusy(true);setError('');try{await onUpload(selected,file)}catch(err:any){setError(err.message)}finally{setBusy(false)}}}/></label>
                        {scene.source==='psd'&&<p className="text-xs text-amber-200">PSD 장면 연출 화면에서 원본과 레이어를 검수하세요. 준비되지 않은 PSD는 제출할 수 없습니다. 이 씬의 합성 완료 영상에는 자체 카메라 효과를 중복 적용하지 않습니다.</p>}
                        <label className="block text-xs">연출 메모<textarea disabled={disabled||busy} value={scene.direction} onChange={e=>update({direction:e.target.value})} maxLength={4000} rows={2} className="mt-1 w-full rounded bg-slate-800 p-2"/></label>
                        <div className="flex flex-wrap gap-2">{MOTION_PRESETS.map(p=><button type="button" key={p.id} disabled={disabled||busy} onClick={()=>update(motionPreset(p.id,scene))} className="rounded border border-cyan-500/40 px-2 py-1 text-xs">{p.label}</button>)}</div>
                        <label className="text-xs">진입 전환 <select disabled={disabled||busy} value={scene.transition} onChange={e=>update({transition:e.target.value as typeof scene.transition})} className="rounded bg-slate-800 p-2"><option value="cut">컷</option><option value="fade">페이드</option><option value="flash">플래시</option></select></label>
                    </div>
                </div>
                {source&&(isVideo?<video ref={video} src={source} preload="auto" muted playsInline className="hidden" onLoadedData={draw} onSeeked={draw}/>:<img ref={image} src={source} alt="" className="hidden" onLoad={draw}/>)}
                <div className="flex items-center gap-3"><button type="button" onClick={()=>{if(time>=1)setTime(0);setPlaying(!playing)}}>{playing?'정지':'구도 재생'}</button><input aria-label="Motion 타임라인 위치" type="range" min="0" max="1" step=".001" value={time} onChange={e=>{setPlaying(false);setTime(Number(e.target.value))}} className="flex-1"/><span className="text-xs">{Math.round(time*100)}%</span></div>
                <div className="space-y-2 rounded border border-white/10 p-3"><p className="text-sm font-semibold">카메라·합성 키프레임</p>{scene.keys.map((k,i)=><div key={i} className="flex flex-wrap items-center gap-2">{keyField(k,'t','시간',0,1,.01)}{keyField(k,'x','X',0,1,.01)}{keyField(k,'y','Y',0,1,.01)}{keyField(k,'scale','확대',1,2,.01)}{keyField(k,'rotation','회전',-8,8,.1)}{keyField(k,'opacity','불투명도',0,100,1)}{i>0&&i<scene.keys.length-1&&<button type="button" disabled={disabled||busy} onClick={()=>update({keys:scene.keys.filter((_,j)=>j!==i)})} className="text-xs text-red-300">삭제</button>}</div>)}<button type="button" disabled={disabled||busy||scene.keys.length>=64} onClick={()=>{if(time<=0||time>=1||scene.keys.some(k=>Math.abs(k.t-time)<.001))return;update({keys:[...scene.keys,{...interpolateMotion(scene.keys,time),t:time}].sort((a,b)=>a.t-b.t)})}} className="text-xs text-cyan-300">현재 위치에 키프레임 추가</button></div>
                <fieldset disabled={disabled||busy} className="space-y-2">
                    <legend className="text-sm font-semibold">효과 트랙</legend>
                    <div className="flex flex-wrap gap-3">{AE_SCENE_EFFECTS.filter(e=>e.id!=='heat_distortion').map(e=><label key={e.id} className="text-xs"><input type="checkbox" checked={scene.effects.some(f=>f.type===e.id)} onChange={ev=>update({effects:ev.target.checked?[...scene.effects,{type:e.id,start:.3,end:.7,intensity:.45,center:[.5,.5],radius:.35,color:[1,.8,.4]}]:scene.effects.filter(f=>f.type!==e.id)})}/> {e.label}</label>)}</div>
                    {scene.effects.map(e=><div key={e.type} className="flex flex-wrap gap-3 rounded bg-slate-900 p-2 text-xs">
                        <span>{AE_SCENE_EFFECTS.find(f=>f.id===e.type)?.label}</span>
                        {(['start','end','intensity','radius'] as const).map(k=><label key={k}>{{start:'시작',end:'종료',intensity:'강도',radius:'반경'}[k]} <input aria-label={`${e.type} ${k}`} type="number" min="0" max="1" step=".01" value={e[k]} onChange={ev=>update({effects:scene.effects.map(f=>f===e?{...f,[k]:Number(ev.target.value)}:f)})} className="w-16 rounded bg-slate-800 p-1"/></label>)}
                        {([0,1] as const).map(axis=><label key={axis}>효과 {axis===0?'X':'Y'} <input aria-label={`${e.type} ${axis===0?'X':'Y'}`} type="number" min="0" max="1" step=".01" value={e.center[axis]} onChange={ev=>update({effects:scene.effects.map(f=>f===e?{...f,center:axis===0?[Number(ev.target.value),f.center[1]]:[f.center[0],Number(ev.target.value)]}:f)})} className="w-16 rounded bg-slate-800 p-1"/></label>)}
                        <label>색상 <input aria-label={`${e.type} 색상`} type="color" value={'#'+e.color.map(v=>Math.round(v*255).toString(16).padStart(2,'0')).join('')} onChange={ev=>{const hex=ev.target.value;update({effects:scene.effects.map(f=>f===e?{...f,color:[parseInt(hex.slice(1,3),16)/255,parseInt(hex.slice(3,5),16)/255,parseInt(hex.slice(5,7),16)/255]}:f)})}}/></label>
                    </div>)}
                </fieldset>
                {scene.source==='psd'&&<section className="space-y-2 rounded border border-cyan-500/30 p-3"><p className="text-sm">PSD 개별 레이어 · 위치·깊이·키프레임</p><button type="button" disabled={busy} onClick={()=>void previews('read')} className="text-xs text-cyan-300">준비된 레이어 불러오기</button><p className="text-xs text-slate-400">X·Y 0.5는 원본 위치입니다. 레이어 수정 후 저장하고 PSD 준비를 다시 요청하면 실제 원화 검수를 거쳐 반영됩니다. 레이어 움직임은 AE 미리보기에서 확인합니다.</p>{(preparations.find(p=>p.scene_number===number)?.layers||[]).filter((l:any)=>l.role!=='background').map((l:any)=>{
                    const layer=scene.layers?.[l.id]||{depth:l.depth,keys:l.keys.length?l.keys.map((k:any)=>({...k,x:.5+k.x,y:.5+k.y})):[motionKey(0),motionKey(1)]}
                    const edit=(value:typeof layer)=>update({layers:{...scene.layers,[l.id]:value}})
                    return <details key={l.id} className="rounded bg-slate-900 p-2"><summary className="cursor-pointer text-xs">{l.name} · {l.role}</summary><label className="text-xs">깊이 <input disabled={disabled||busy} type="number" min="0" max="1" step=".01" value={layer.depth} onChange={e=>edit({...layer,depth:Number(e.target.value)})} className="w-20 bg-slate-800 p-1"/></label>{layer.keys.map((key:MotionKey,i:number)=><div key={i} className="mt-2 flex flex-wrap gap-2">{(['t','x','y','scale','rotation','opacity'] as const).map(field=><label key={field} className="text-xs">{field}<input disabled={disabled||busy} aria-label={`${l.name} ${i} ${field}`} type="number" step=".01" value={key[field]} onChange={e=>edit({...layer,keys:layer.keys.map((k:MotionKey,j:number)=>j===i?{...k,[field]:Number(e.target.value)}:k)})} className="ml-1 w-16 bg-slate-800 p-1"/></label>)}</div>)}<button type="button" disabled={disabled||busy||layer.keys.length>=64} className="mt-2 text-xs text-cyan-300" onClick={()=>{if(time<=0||time>=1||layer.keys.some((k:MotionKey)=>Math.abs(k.t-time)<.001))return;edit({...layer,keys:[...layer.keys,{...interpolateMotion(layer.keys,time),t:time}].sort((a:MotionKey,b:MotionKey)=>a.t-b.t)})}}>현재 위치에 레이어 키프레임 추가</button></details>
                })}</section>}
                <div className="flex flex-wrap gap-3 text-xs"><button type="button" disabled={disabled||busy||!draft.enabled} onClick={()=>void previews('preview')} className="rounded bg-cyan-800 px-3 py-2">저해상도 MP4 미리보기 요청</button><button type="button" disabled={busy} onClick={()=>void previews('read')}>미리보기 상태 새로고침</button></div>
                <button type="button" disabled={disabled||busy||!draft.enabled||scene.source==='psd'} onClick={()=>void previews('direction')} className="rounded border border-cyan-400/40 px-3 py-2 text-xs">Codex 감독 · 원본 분석 후 연출 초안</button>
                {jobs.filter(j=>j.scene_number===number).map(j=><div key={j.id} className="text-xs">{j.state} {j.error}{j.suggestion&&<div className="mt-2 rounded bg-slate-900 p-2"><p>{j.suggestion.evidence?.join(' · ')}</p><button type="button" disabled={disabled||busy} className="mt-2 text-cyan-300" onClick={()=>{try{const valid=normalizeMotionDraft({...draft,scenes:{...draft.scenes,[number]:j.suggestion.scene}});setDraft(valid);setNotice('감독 초안을 편집기에 반영했습니다. 확인 후 저장해 주세요.')}catch(e:any){setError(e.message)}}}>감독 초안을 편집기에 적용</button></div>}{j.url&&<video controls src={j.url} className="mt-2 max-h-80 max-w-full"/>}</div>)}
            </>}
            {notice&&<p role="status" className="text-xs text-cyan-200">{notice}</p>}{error&&<p role="alert" className="text-sm text-red-300">{error}</p>}
            {renderHistory.filter(r=>r.status==='completed').map(r=>{
                const m=r.metadata||{},url=m.gcs_bucket&&m.gcs_path?`/api/std/assets/gcs-file?bucket=${encodeURIComponent(m.gcs_bucket)}&path=${encodeURIComponent(m.gcs_path)}`:m.result_public_url||m.gcs_public_url
                return url?<details key={r.id} className="rounded border border-emerald-500/30 p-3"><summary className="cursor-pointer text-sm text-emerald-200">최종 합성 영상 v{r.render_version} · 실제 출력 검토</summary><p className="my-2 text-xs text-slate-400">음성·자막·장면 경계와 피사체 가림을 실제 영상에서 확인하세요. 미리보기 및 렌더 완료는 검수 승인과 별개입니다.</p><video controls preload="metadata" src={url} className="max-h-[500px] w-full"/></details>:null
            })}
        </div>}
    </details></>
}
