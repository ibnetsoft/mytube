'use client'
import { useEffect, useRef, useState } from 'react'
import { wuxiaClipPrompt, wuxiaClipStates } from '@/lib/stdWuxiaClips'

export default function StdWuxiaClipEditor({ project, sceneNumber, subtitles, headers, onChange }: {
    project: any; sceneNumber: number; subtitles: any[]; headers: Record<string,string>;
    onChange: (clipPayload: any, assets: any[], updatedAt: string) => void
}) {
    const states = wuxiaClipStates(project, sceneNumber)
    const fileReadVersion=useRef(0)
    const [stateId,setStateId] = useState(''), [file,setFile] = useState<File|null>(null)
    const [info,setInfo] = useState<any>(null), [sourceIn,setSourceIn] = useState(0), [length,setLength] = useState(3)
    const [offset,setOffset] = useState(0), [busy,setBusy] = useState(false), [message,setMessage] = useState('')
    const [poster,setPoster] = useState(''), [retryId,setRetryId] = useState('')
    const state = states.find(s=>s.asset_id===stateId) || states[0]
    const rows = subtitles.filter(r=>Number(r.scene_number)===sceneNumber)
    const scene = project.project_payload?.structure?.wuxia_ae_package?.scenes?.find((s:any)=>Number(String(s.scene_id).match(/S(\d+)$/)?.[1])===sceneNumber)
    const total = rows.length ? Math.max(...rows.map(r=>Number(r.end_num??r.end_time??r.end)))-Math.min(...rows.map(r=>Number(r.start_num??r.start_time??r.start))) : Number(scene?.preview_duration_seconds||0)
    const windowSeconds = state ? (Number(state.end??1)-Number(state.start||0))*total : 0
    const clip = project.project_payload?.wuxia_state_clips?.[state?.asset_id]
    const attachedId=clip?.asset_id||project.project_payload?.wuxia_state_clip_restore_ids?.[state?.asset_id]
    const locked = ['approved','canceled','review_requested'].includes(project.status)
    useEffect(()=>{setStateId('');setFile(null);setInfo(null);setMessage('');setRetryId('')},[project.id,sceneNumber])
    useEffect(()=>{
        fileReadVersion.current++;setPoster('');if(!state)return
        const controller=new AbortController();let url=''
        const src=String(state.media_url||state.image_url||'')
        void fetch(src,{headers:src.startsWith('/')?headers:undefined,signal:controller.signal}).then(r=>{if(!r.ok)throw Error('원화 다운로드 실패');return r.blob()})
            .then(blob=>{if(!controller.signal.aborted){url=URL.createObjectURL(blob);setPoster(url)}}).catch(()=>{})
        return()=>{controller.abort();if(url)URL.revokeObjectURL(url)}
    },[state?.sha256,headers])
    async function readFile(next:File|null){
        const version=++fileReadVersion.current
        setFile(null);setInfo(null);setMessage('');setRetryId('');if(!next)return
        const url=URL.createObjectURL(next),video=document.createElement('video')
        try{
            const result=await new Promise<any>((resolve,reject)=>{
                video.preload='metadata';video.onloadedmetadata=()=>resolve({width:video.videoWidth,height:video.videoHeight,duration_seconds:video.duration})
                video.onerror=()=>reject(Error('영상을 읽을 수 없습니다.'));video.src=url
            })
            if(version!==fileReadVersion.current)return
            if((next.type&&next.type!=='video/mp4')||!Number.isFinite(result.duration_seconds)||result.duration_seconds<=0||result.duration_seconds>30||Math.abs(result.width/result.height-16/9)>.01||next.size>250*1024*1024)throw Error('16:9 H.264 MP4, 최대 30초·250MB 영상을 선택해 주세요.')
            setFile(next);setInfo(result);setSourceIn(0);setOffset(0);setLength(Math.floor(Math.min(result.duration_seconds,windowSeconds,5)*1000)/1000)
        }catch(error:any){setMessage(error.message)}finally{video.removeAttribute('src');video.load();URL.revokeObjectURL(url)}
    }
    async function refresh(){
        const response=await fetch(`/api/std/projects/${project.id}`,{headers:{...headers,'x-std-refresh':'1'},cache:'no-store'})
        const data=await response.json();if(!response.ok)throw Error(data.error||'저장 재조회 실패')
        const p=data.project.project_payload
        onChange({wuxia_state_clips:p.wuxia_state_clips||{},wuxia_state_clip_issues:p.wuxia_state_clip_issues||[],wuxia_state_clip_restore_ids:p.wuxia_state_clip_restore_ids||{}},data.assets||[],data.project.updated_at)
    }
    async function attach(id:string,action='complete'){
        const response=await fetch(`/api/std/projects/${project.id}/wuxia-clips`,{method:'PATCH',headers,body:JSON.stringify({asset_id:id,action})})
        const data=await response.json();if(!response.ok)throw Error(data.error||'영상 연결 실패')
        await refresh();setRetryId('');setMessage(action==='disable'?'원화로 복원했습니다. 영상 파일은 보존됩니다.':'해당 상태 컷에 영상을 연결했습니다. 미리보기에서 전체 구간을 확인해 주세요.')
    }
    async function upload(){
        if(!file||!info||!state)return
        if(length<=0||sourceIn<0||offset<0||sourceIn+length>info.duration_seconds+1e-6||offset+length>windowSeconds+1e-6){setMessage('영상 원본과 상태 컷 안에 들어가는 사용 구간을 지정해 주세요.');return}
        setBusy(true);setMessage('영상을 업로드하고 있습니다.')
        try{
            const sha256=Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',await file.arrayBuffer())),n=>n.toString(16).padStart(2,'0')).join('')
            const response=await fetch(`/api/std/projects/${project.id}/wuxia-clips`,{method:'POST',headers,body:JSON.stringify({...info,
                state_asset_id:state.asset_id,source_state_sha256:state.sha256,sha256,file_size:file.size,
                mime_type:file.type||'video/mp4',source_in_seconds:sourceIn,play_seconds:length,start_offset_seconds:offset})})
            const data=await response.json();if(!response.ok)throw Error(data.error||'업로드 준비 실패')
            const uploaded=await fetch(data.upload_url,{method:'PUT',headers:{'Content-Type':file.type||'video/mp4'},body:file})
            if(!uploaded.ok)throw Error('파일 업로드 실패. 원화는 유지됩니다.')
            setRetryId(data.asset_id);await attach(data.asset_id)
        }catch(error:any){setMessage(error.message)}finally{setBusy(false)}
    }
    return <details className="rounded border border-cyan-700/50 bg-cyan-950/20 p-3 text-xs text-cyan-100">
        <summary className="cursor-pointer font-bold">씬 {sceneNumber} · 상태 컷 영상 교체</summary>
        {project.project_payload?.wuxia_state_clip_issues?.map((issue:string)=><p role="alert" key={issue} className="text-red-300">{issue}</p>)}
        {!state?<p>이 씬의 상태 원화를 찾을 수 없습니다.</p>:<div className="mt-3 space-y-2">
            <label>교체할 원화 <select aria-label="영상으로 교체할 상태 컷" className="w-full bg-slate-900 p-2" value={state.asset_id} disabled={busy} onChange={e=>{setStateId(e.target.value);setFile(null);setInfo(null);setRetryId('')}}>{states.map(s=><option key={s.asset_id} value={s.asset_id}>{s.asset_id}</option>)}</select></label>
            {poster&&<><img src={poster} alt={`${state.asset_id} 영상 생성 기준 원화`} className="max-h-36 w-full object-contain"/><a className="underline" href={poster} download={`${state.asset_id}.png`}>기준 원화 다운로드</a></>}
            <p>원화 구간 {windowSeconds.toFixed(2)}초 · {rows.length?'현재 음성 타이밍':'가편집 타이밍'}. 원화와 확정 음성은 유지하고 선택한 구간만 정상 속도로 재생합니다. 영상 원본 소리는 사용하지 않습니다.</p>
            <textarea aria-label="원화 기준 영상 생성 프롬프트" readOnly value={wuxiaClipPrompt(state)} rows={5} className="w-full rounded bg-slate-900 p-2"/>
            <button type="button" className="rounded bg-slate-700 px-3 py-1" onClick={()=>void navigator.clipboard.writeText(wuxiaClipPrompt(state)).then(()=>setMessage('프롬프트를 복사했습니다.'),()=>setMessage('복사하지 못했습니다. 프롬프트를 직접 선택해 주세요.'))}>프롬프트 복사</button>
            {locked?<p>프로젝트를 편집 가능한 상태로 다시 열면 영상을 연결할 수 있습니다.</p>:<>
                <input aria-label="상태 컷 영상 파일" type="file" accept="video/mp4,.mp4" disabled={busy} onChange={e=>void readFile(e.target.files?.[0]||null)}/>
                {info&&<div className="grid grid-cols-3 gap-2">{[['원본 시작(초)',sourceIn,setSourceIn],['사용 길이(초)',length,setLength],['원화 내 시작(초)',offset,setOffset]].map(([label,value,setter]:any)=><label key={label}>{label}<input className="w-full bg-slate-900 p-1" type="number" min="0" step="0.001" value={value} disabled={busy} onChange={e=>setter(Number(e.target.value))}/></label>)}</div>}
                <button type="button" disabled={!file||busy} className="rounded bg-cyan-800 px-3 py-2 disabled:opacity-40" onClick={()=>void upload()}>영상 업로드·연결</button>
                {retryId&&<button type="button" disabled={busy} onClick={()=>{setBusy(true);void attach(retryId).catch(e=>setMessage(e.message)).finally(()=>setBusy(false))}}>연결 재시도</button>}
                {attachedId&&<button type="button" disabled={busy} className="ml-2 underline" onClick={()=>{setBusy(true);void attach(attachedId,'disable').catch(e=>setMessage(e.message)).finally(()=>setBusy(false))}}>원화로 복원</button>}
            </>}
            <p role="status">{message|| (clip?'영상 연결됨 · 원화·인물·소품과 다음 컷의 연결을 검토해 주세요.':'선택한 원화를 생성 도구에 첨부한 뒤, 완성한 클립을 여기 업로드하세요.')}</p>
        </div>}
    </details>
}
