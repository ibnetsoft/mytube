'use client'
import { useEffect, useState } from 'react'

export default function AiSfxPlanButton({ projectId, headers, appliedJobId, subtitles, beforeSave, onApplied }: {
    projectId: string; headers: Record<string,string>; appliedJobId?: string; subtitles: any[];
    beforeSave: () => Promise<any>; onApplied: () => Promise<any>;
}) {
    const [job, setJob] = useState<any>(null)
    const [busy, setBusy] = useState(false)
    const [error, setError] = useState('')
    const key = JSON.stringify(headers)
    const endpoint = `/api/std/projects/${encodeURIComponent(projectId)}/sfx-plan`
    useEffect(() => {
        let cancelled = false
        const controller = new AbortController()
        const poll = async () => {
            try {
                const response = await fetch(endpoint, { headers: JSON.parse(key), signal: controller.signal })
                const data = await response.json()
                if (!cancelled && response.ok) setJob(data.job)
            } catch { /* Retry status reads only; never re-enqueue automatically. */ }
        }
        void poll()
        const timer = job && ['pending','claimed','rendering','running'].includes(job.status) ? setInterval(poll, 6000) : null
        return () => { cancelled = true; controller.abort(); if (timer) clearInterval(timer) }
    }, [endpoint, key, job?.id, job?.status])
    const run = async (apply: boolean) => {
        setBusy(true); setError('')
        try {
            await beforeSave()
            const response = await fetch(endpoint, { method:'POST', headers: { ...headers, 'Content-Type':'application/json' },
                body: JSON.stringify({ ...(apply ? { action:'apply', job_id:job.id } : { action:'generate' }), subtitles }) })
            const data = await response.json()
            if (!response.ok) throw new Error(data.error || '효과음 구성 실패')
            if (apply) await onApplied()
            else setJob(data.job)
        } catch (e: any) { setError(e.message) }
        finally { setBusy(false) }
    }
    const pending = job && ['pending','claimed','rendering','running'].includes(job.status)
    return <div className="space-y-2 rounded border border-purple-400/25 p-2 text-xs">
        <button type="button" disabled={busy || pending} onClick={() => void run(false)}
            className="rounded bg-purple-600 px-3 py-2 text-white disabled:opacity-50">
            {pending ? '대본 워커가 효과음 구성 중…' : 'AI 효과음 구성'}
        </button>
        <p className="text-gray-400">저장된 효과음만 사용 · 수동 배치 유지 · 음성 재생성 없음</p>
        {job?.status === 'completed' && job.id !== appliedJobId && <div>
            <p className="text-purple-200">추천 {job.result_payload?.cues?.length || 0}개</p>
            {(job.result_payload?.cues || []).map((c: any) => <p key={c.id} className="my-1 text-gray-300">Scene {c.scene_number} · {c.file_name} — {c.reason}</p>)}
            <button type="button" disabled={busy} onClick={() => void run(true)} className="rounded bg-emerald-700 px-3 py-2">구성 적용</button>
        </div>}
        {job?.status === 'failed' && <p className="text-amber-300">구성 실패: {job.error_message || '다시 시도해 주세요.'}</p>}
        {error && <p role="alert" className="text-amber-300">{error}</p>}
    </div>
}
