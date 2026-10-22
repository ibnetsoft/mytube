'use client'
import { useEffect, useState } from 'react'
import { startVisiblePolling } from '@/lib/stdVisiblePolling'

export default function StdMouthPreviews({ projectId, headers }: { projectId: string; headers: Record<string, string> }) {
    const [data, setData] = useState<any>(null), [error, setError] = useState(''), [busy, setBusy] = useState(false)
    const [pipeline, setPipeline] = useState<any>(null)
    const [media, setMedia] = useState<{ number: number; url: string } | null>(null)
    const signature = JSON.stringify(headers)
    useEffect(() => {
        const abort = new AbortController()
        const read = async (signal: AbortSignal) => {
            try {
                const response = await fetch(`/api/std/projects/${projectId}/ae-mouth`, { headers: JSON.parse(signature), signal })
                const next = await response.json()
                if (!response.ok) throw Error(next.error || 'State request failed')
                if (!abort.signal.aborted && !signal.aborted) setData(next)
                const run = await fetch(`/api/std/projects/${projectId}/pipeline`, { headers: JSON.parse(signature), signal })
                if (!run.ok) throw Error('Pipeline request failed')
                const pipeline = await run.json()
                if (!abort.signal.aborted && !signal.aborted) setPipeline(pipeline)
            } catch (error) { throw error }
        }
        const stop = startVisiblePolling(read, 15000)
        return () => { stop(); abort.abort() }
    }, [projectId, signature])
    useEffect(() => () => { if (media) URL.revokeObjectURL(media.url) }, [media])
    const prepare = async () => {
        setBusy(true); setError('')
        try {
            const response = await fetch(`/api/std/projects/${projectId}/ae-mouth`, {
                method: 'POST', headers: { ...headers, 'Content-Type': 'application/json' }, body: JSON.stringify({ action: 'prepare_preview' }),
            })
            const result = await response.json()
            if (!response.ok) throw new Error(result.error)
            setData((old: any) => ({ ...old, status: 'queued' }))
        } catch (e: any) { setError(e.message) }
        finally { setBusy(false) }
    }
    const play = async (row: any) => {
        try {
            const response = await fetch(row.videoUrl, { headers })
            if (!response.ok) throw new Error('영상 파일을 불러오지 못했습니다.')
            setMedia({ number: row.number, url: URL.createObjectURL(await response.blob()) })
        } catch (e: any) { setError(e.message) }
    }
    const ready = (data?.results || []).filter((r: any) => r.status === 'artifact_ready' && r.videoUrl)
    return <div className="mt-3 rounded-lg border border-white/10 p-3">
        <p className="text-sm font-semibold">성우 음성에 맞춘 입모양 영상</p>
        <p className="text-xs text-gray-400">음성 생성 후 자동 준비됩니다. 영상·화자를 바꿨다면 다시 준비해 주세요. 제출 후에는 저장한 설정으로 조립합니다.</p>
        <button type="button" disabled={busy} onClick={prepare} className="mt-2 rounded bg-blue-600 px-3 py-1 text-sm">{busy ? '요청 중…' : '입모양 영상 준비'}</button>
        <span className="ml-2 text-xs">{ready.length}개 준비됨{['processing','queued'].includes(data?.status) ? ' · 합성 중' : ''}</span>
        {pipeline?.warning && <p className="mt-2 text-xs text-amber-200" role="status">{pipeline.warning}</p>}
        {pipeline?.run && <p className="mt-2 text-xs" role="status">{pipeline.render?.message || (pipeline.run.status === 'input_error' ? '필수 입력 또는 실행 오류가 있습니다.' : '저장된 설정으로 영상 준비 중')}{pipeline.render?.progress != null ? ` · ${pipeline.render.progress}%` : ''}</p>}
        {error && <p role="alert" className="text-sm text-red-300">{error}</p>}
        <div className="mt-2 flex flex-wrap gap-2">{ready.map((r: any) => <button type="button" key={r.number} onClick={() => play(r)} className="rounded border border-white/20 px-2 py-1 text-xs">#{r.number} 영상 보기</button>)}</div>
        {media && <video key={media.url} src={media.url} controls playsInline className="mt-2 w-full rounded" aria-label={`${media.number}번 음성 싱크 영상`} />}
    </div>
}
