 'use client'
import { useEffect, useState } from 'react'
export default function StdSpeakerCoordinates({projectId, revision, headers}:{projectId:string;revision:string;headers:Record<string,string>}) {
    const [status,setStatus] = useState('준비 상태 확인 중…')
    const [retry,setRetry] = useState(0)
    useEffect(() => {
        const controller = new AbortController(); let timer:ReturnType<typeof setTimeout>
        const check = async () => {
            try {
                const response = await fetch(`/api/std/projects/${projectId}/speaker-coordinates`,{method:'POST',headers,body:JSON.stringify({retry:retry>0}),signal:controller.signal})
                const result = await response.json()
                if (!response.ok) throw new Error(result.error || '캐릭터 확인 준비 실패')
                const done = result.results?.length || 0
                setStatus(result.state === 'ready' ? `확인 완료 (${result.count}개 대사씬)` : result.state === 'needs_review' ? `추가 확인 필요: ${result.error}` : `확인 준비 중 (${done}/${result.count})`)
                if (['queued','processing'].includes(result.state)) timer = setTimeout(check,20000)
            } catch(error:any) { if(!controller.signal.aborted) setStatus(error.message) }
        }
        timer=setTimeout(check,1500)
        return () => {controller.abort();clearTimeout(timer)}
    },[projectId,revision,retry])
    return <aside aria-label="대사씬 캐릭터 확인" className="fixed bottom-4 right-4 z-[60] w-[min(360px,calc(100vw-32px))] rounded-xl border border-cyan-500/40 bg-[#10252d] p-3 text-cyan-200 shadow-lg">
        <div className="flex items-center justify-between gap-3">
            <h2 className="text-sm font-bold">대사씬 캐릭터 확인</h2>
            <button type="button" onClick={()=>setRetry(n=>n+1)} className="shrink-0 text-xs underline">새로 확인</button>
        </div>
        <p className="mt-1 max-h-16 overflow-y-auto break-words text-xs" role="status">{status}</p>
    </aside>
}
