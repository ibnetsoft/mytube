 'use client'
import { useEffect, useState } from 'react'
export default function StdSpeakerCoordinates({projectId, revision, headers}:{projectId:string;revision:string;headers:Record<string,string>}) {
    const [status,setStatus] = useState('얼굴·입 위치 준비 상태 확인 중…')
    const [retry,setRetry] = useState(0)
    useEffect(() => {
        const controller = new AbortController(); let timer:ReturnType<typeof setTimeout>
        const check = async () => {
            try {
                const response = await fetch(`/api/std/projects/${projectId}/speaker-coordinates`,{method:'POST',headers,body:JSON.stringify({retry:retry>0}),signal:controller.signal})
                const result = await response.json()
                if (!response.ok) throw new Error(result.error || '입 위치 준비 실패')
                const done = result.results?.length || 0
                setStatus(result.state === 'ready' ? `얼굴·입 위치 저장 완료 (${result.count}개 대사 씬)` : result.state === 'needs_review' ? `입 위치 확인 필요: ${result.error}` : `얼굴·입 위치 미리 준비 중 (${done}/${result.count})`)
                if (['queued','processing'].includes(result.state)) timer = setTimeout(check,20000)
            } catch(error:any) { if(!controller.signal.aborted) setStatus(error.message) }
        }
        timer=setTimeout(check,1500)
        return () => {controller.abort();clearTimeout(timer)}
    },[projectId,revision,retry])
    return <div className="mt-2 text-xs text-cyan-200" role="status">{status}<button type="button" onClick={()=>setRetry(n=>n+1)} className="ml-2 underline">새로 확인</button></div>
}
