import React, {useEffect, useMemo, useRef, useState} from 'react'
import {createRoot} from 'react-dom/client'
import StdMotionStudio from '../../auth-web/components/StdMotionStudio'
import StdAeScenePreparation from '../../auth-web/components/StdAeScenePreparation'
import StdComicEditor from '../../auth-web/components/StdComicEditor'
import StdVideoModelSettings from '../../auth-web/components/StdVideoModelSettings'
import StdSpeakerCoordinates from '../../auth-web/components/StdSpeakerCoordinates'

const preparing=document.getElementById('local-production-settings')?.dataset.workerStage==='preparation'
const token = document.querySelector<HTMLMetaElement>('meta[name="local-token"]')!.content
const localHeaders = {'X-Codex-Local':token}
async function request(url:string, headers:Record<string,string>, body?:object, signal?:AbortSignal) {
    const response = await fetch(url,{headers:{...headers,'Content-Type':'application/json'},signal,...(body?{method:'POST',body:JSON.stringify(body)}:{})})
    const data=await response.json()
    if(!response.ok)throw Error(data.error||'제작 설정을 처리하지 못했습니다.')
    return data
}
function ProductionSettings() {
    const [projects,setProjects]=useState<any[]>([]), [id,setId]=useState(''), [data,setData]=useState<any>(null)
    const [error,setError]=useState(''),[loading,setLoading]=useState(false),[tab,setTab]=useState<'production'|'models'|'status'>(preparing?'production':'status')
    const [password,setPassword]=useState(''),[connecting,setConnecting]=useState(false),[connection,setConnection]=useState(''),[connectionVersion,setConnectionVersion]=useState(0)
    const [overview,setOverview]=useState<any>(null),[execution,setExecution]=useState<any[]>([])
    const version=useRef(''), active=useRef('')
    const headers=useMemo(()=>({...localHeaders,'X-Local-Project':id}),[id])
    const list=async()=>{setError('');try{setProjects((await request('/api/local/projects',localHeaders)).projects)}catch(e:any){setError(e.message)}}
    useEffect(()=>{void list()},[])
    useEffect(()=>{
        active.current=id;setData(null);setPassword('');setConnection('');version.current='';if(!id)return
        const abort=new AbortController();setLoading(true);setError('')
        void request(`/api/local/projects/${id}`,headers,undefined,abort.signal).then(value=>{if(!abort.signal.aborted){version.current=value.project.updated_at;setData(value)}}).catch(e=>{if(!abort.signal.aborted)setError(e.message)}).finally(()=>{if(!abort.signal.aborted)setLoading(false)})
        return()=>abort.abort()
    },[id,headers])
    const save=async(changes:object)=>{
        const current=id
        const result=await request(`/api/local/projects/${id}/settings`,headers,{...changes,version:version.current})
        if(active.current===current){version.current=result.updated_at;setData((d:any)=>({...d,project:{...d.project,updated_at:result.updated_at,render_settings:result.render_settings}}))}
    }
    const upload=async(scene:any,file:File)=>{
        const spec={scene_number:scene.scene_number,asset_type:file.type.startsWith('video/')?'video':'image',file_name:file.name,mime_type:file.type,file_size:file.size}
        const init=await request(`/api/std/projects/${id}/assets/init`,headers,spec)
        const response=await fetch(init.storage_upload_url,{method:'PUT',headers:{'Content-Type':spec.mime_type},body:file})
        if(!response.ok)throw Error('파일 업로드에 실패했습니다.')
        const result=await request(`/api/std/projects/${id}/assets/complete`,headers,{...spec,storage_provider:'gcs',storage_bucket:init.storage_bucket,storage_path:init.storage_path})
        // Upload completion can update the project version. Reload before the next settings save.
        const refreshed=await request(`/api/local/projects/${id}`,headers)
        if(active.current===id){version.current=refreshed.project.updated_at;setData(refreshed)}
        return result
    }
    const readCoordinates=async()=>{try{setOverview(await request(`/api/std/projects/${id}/speaker-coordinates`,headers,{}))}catch(e:any){setError(e.message)}}
    const readExecution=async()=>{try{setExecution((await request(`/api/local/projects/${id}/jobs`,headers)).jobs)}catch(e:any){setError(e.message)}}
    useEffect(()=>{setOverview(null);setExecution([]);if(!data)return;if(preparing)void readCoordinates();else if(data.project.submitted_at)void readExecution()},[id,data?.project.id])
    const settings=data?.project.render_settings||{}
    return <div className="space-y-5 text-sm text-white">
        <div className="flex flex-wrap gap-3 items-end"><label className="flex-1">제작할 프로젝트<select aria-label="제작할 프로젝트" value={id} onChange={e=>setId(e.target.value)} className="mt-2 block w-full rounded bg-slate-800 p-3"><option value="">프로젝트 선택</option>{projects.map(p=><option key={p.id} value={p.id}>{p.title||'이름 없는 프로젝트'} · {p.employee_email}{p.submitted_at?' · 제출됨':''}</option>)}</select></label><button type="button" onClick={()=>void list()} className="rounded border border-white/20 p-3">목록 새로고침</button></div>
        {loading&&<p role="status">프로젝트 설정을 불러오는 중…</p>}{error&&<p role="alert" className="text-red-300">{error}</p>}
        {data&&<><p className="text-slate-300">설정 계정: {data.project.employee_email} · {data.project.title}</p>{!preparing&&!data.project.submitted_at&&<p className="text-amber-300">제출 전 프로젝트입니다. 원본·좌표·연출 준비는 대본워커에서, 영상 제작·화자 지정은 유저웹에서 진행하세요. 통합워커는 제출 후 실행합니다.</p>}
            <nav aria-label="제작 설정 종류" className="flex gap-3">{preparing?<button onClick={()=>setTab('production')} className="rounded bg-cyan-900 p-3">원본·좌표·AE 연출 준비</button>:<><button onClick={()=>setTab('status')} className="rounded bg-cyan-900 p-3">제출 후 실행·검수 상태</button><button onClick={()=>setTab('models')} className="rounded bg-cyan-900 p-3">영상 생성 모델 · API</button></>}</nav>
            {!preparing&&tab==='status'?<section className="space-y-3 rounded border border-cyan-400/30 p-4"><h3>AE 실행 · 출력 검수 · 최종 렌더</h3><p>제출된 원본·화자·음성과 준비된 연출을 사용합니다. 새 이미지·좌표·레이어는 생성하지 않습니다.</p>{data.project.submitted_at&&<><button onClick={()=>void readExecution()} className="rounded bg-cyan-800 p-2">실행 상태 새로고침</button>{execution.length===0&&<p>등록된 후반 작업이 없습니다. 아래 AE·렌더 작업 목록을 확인하세요.</p>}{execution.map(job=><div key={job.id} className="rounded border border-white/15 p-3"><strong>{job.kind} · {job.state}</strong><p>{job.phase} {job.progress} · 완료 {job.done}/{job.total}</p>{job.error&&<p className="text-amber-300">{job.error}</p>}</div>)}</>}</section>:!preparing&&tab==='models'?<>
                <details className="rounded border border-white/20 p-4"><summary className="cursor-pointer">기존 영상 API 설정 계정 연결</summary><p className="mt-3 text-slate-300">기존 설정을 불러오려면 이 워커 안에서 계정을 연결하세요. 비밀번호는 저장하지 않으며, 연결은 워커가 종료될 때 해제됩니다.</p><form className="mt-3 space-y-3" onSubmit={async event=>{event.preventDefault();setConnecting(true);setConnection('');try{await request('/api/local/account-login',headers,{password});setPassword('');setConnection('계정 연결 완료');setConnectionVersion(v=>v+1)}catch(e:any){setConnection(e.message)}finally{setConnecting(false)}}}><label className="block">연결 계정<input readOnly value={data.project.employee_email} className="ml-3 rounded bg-slate-800 p-2"/></label><label className="block">비밀번호 / PIN<input type="password" autoComplete="current-password" value={password} onChange={e=>setPassword(e.target.value)} required className="ml-3 rounded bg-slate-800 p-2"/></label><button disabled={connecting} className="rounded bg-cyan-800 p-2">{connecting?'연결 중…':'이 워커에서 계정 연결'}</button><p role="status">{connection}</p></form></details>
                <StdVideoModelSettings key={`${id}-${connectionVersion}`} headers={headers}/>
            </>:<>
                <section className="space-y-3 rounded border border-cyan-400/30 p-4"><h3>이미지·얼굴·입 좌표 준비</h3><p>생성된 원본 이미지와 좌표·입모양 소재를 준비합니다. 최종 화자 지정과 이미지의 영상화는 유저웹에서 진행합니다.</p><button onClick={()=>void readCoordinates()} className="rounded bg-cyan-800 p-2">원본·좌표 상태 새로고침</button>{overview?.scenes?.map((scene:any)=><div key={scene.number} className="rounded border border-white/15 p-3"><span>씬 {scene.number} · {scene.image?'원본 준비됨':'원본 이미지 필요'} · {scene.analysisState||scene.result?.origin||'좌표 준비 대기'}</span><button disabled={!scene.image||['queued','processing'].includes(scene.analysisState)} onClick={async()=>{try{setOverview(await request(`/api/std/projects/${id}/speaker-coordinates`,headers,{action:'analyze',sceneNumber:scene.number}))}catch(e:any){setError(e.message)}}} className="ml-3 rounded bg-cyan-800 p-2">얼굴·입 좌표 준비 요청</button></div>)}</section>
                <StdMotionStudio preparationOnly key={id} value={settings.motion} scenes={data.scenes} disabled={!data.editable} projectId={id} headers={headers} defaultAspect={settings.comic?.mode==='webtoon_video'?'9:16':'16:9'} onSave={motion=>save({motion})} onUpload={upload} aePreparation={<StdAeScenePreparation projectId={id} headers={headers}/>}/>
                <StdSpeakerCoordinates preparationOnly projectId={id} revision={data.project.updated_at} headers={headers}/>
                <StdComicEditor key={`comic-${id}`} value={settings.comic} scenes={data.scenes} subtitles={data.project.subtitles} disabled={!data.editable} onSave={comic=>save({comic})} onUpload={upload}/>
            </>}
        </>}
    </div>
}
const section=document.getElementById('local-production-settings')!
let mounted=false
const mount=()=>{if((section as HTMLDetailsElement).open&&!mounted){mounted=true;createRoot(document.getElementById('production-settings-root')!).render(<ProductionSettings/>)}}
section.addEventListener('toggle',mount);mount()
