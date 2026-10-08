'use client'

import { useCallback, useEffect, useState } from 'react'

export default function StdAeMouthPanel({ projectId, headers }: { projectId: string; headers: Record<string, string> }) {
    const [data, setData] = useState<any>(null), [error, setError] = useState(''), [busy, setBusy] = useState(false)
    const load = useCallback(async () => {
        try {
            const res = await fetch(`/api/std/projects/${projectId}/ae-mouth`, { headers })
            const body = await res.json()
            if (!res.ok) throw new Error(body.error)
            setData(body)
        } catch (e: any) { setError(e.message || 'AE 작업 조회 실패') }
    }, [projectId, headers])
    useEffect(() => { void load(); const timer = setInterval(() => void load(), 15000); return () => clearInterval(timer) }, [load])
    const action = async (kind: string, number?: number) => {
        let reason = ''
        if (kind === 'exclude') { reason = window.prompt('이 씬에서 입모양 작업을 제외하는 사유를 적어 주세요.') || ''; if (!reason) return }
        setBusy(true); setError('')
        try {
            const res = await fetch(`/api/std/projects/${projectId}/ae-mouth`, { method: 'POST', headers: { ...headers, 'Content-Type': 'application/json' },
                body: JSON.stringify({ action: kind, number, reason, fingerprint: data.fingerprint }) })
            const body = await res.json()
            if (!res.ok) throw new Error(body.error)
            await load()
        } catch (e: any) { setError(e.message || 'AE 검수 실패') } finally { setBusy(false) }
    }
    if (!data?.applicable) return null
    const status: Record<string, string> = { not_started: '제출 후 시작', queued: '작업 대기', processing: '대사 판별·AE 처리 중', direction_pending: '씬별 작업 지침 승인 필요', direction_approved: 'AE 작업 대기', review_pending: '결과 검수 필요', reviewed: '검수 완료', failed: '작업 실패', obsolete: '원본 변경 · 다시 제출 필요' }
    return <section className="my-4 rounded-xl border border-white/15 p-4">
        <h3 className="font-semibold">19씬 이후 · AE 입모양 후작업</h3>
        <p className="mt-2 text-sm text-gray-400">제출하면 실제 대사와 화면 속 화자를 판별합니다. 씬별 지침 승인 후 확정된 음성에 맞춰 화자의 입모양을 바꾸고 기존 AE 효과와 합성합니다. 결과를 검수한 뒤 최종 렌더링을 제출해 주세요.</p>
        <p className="mt-2 text-sm">{status[data.status] || data.status}</p>
        {(error || data.preparationError || data.error) && <p role="alert" className="mt-2 text-sm text-red-400">{error || data.preparationError || data.error}</p>}
        {data.status === 'failed' && <button disabled={busy} onClick={() => void action('retry')} className="mt-2 rounded bg-white/10 px-3 py-2 text-sm">실패 작업 재시도</button>}
        {data.results?.map((r: any) => <article key={r.number} className="mt-3 rounded border border-white/10 p-3">
            <p className="text-sm">{r.number}번 씬 · {r.speakers.join(', ') || '화자 없음'} · {r.status === 'approved' ? '승인 완료' : r.status === 'skipped' ? '입모양 제외' : r.status === 'needs_review' ? '화자·입 위치 검토 필요' : r.status === 'direction_pending' ? '지침 승인 대기' : '검수 대기'}</p>
            <p className="mt-1 text-sm text-gray-400">{r.direction || r.reason}</p>
            {r.videoUrl && <video className="mt-2 w-full max-w-2xl" controls preload="metadata" src={r.videoUrl} />}
            {r.status === 'review_pending' && <button disabled={busy} onClick={() => void action('review', r.number)} className="mt-2 rounded bg-indigo-600 px-3 py-2 text-sm">입모양·AE 결과 승인</button>}
            {r.status === 'needs_review' && <button disabled={busy} onClick={() => void action('exclude', r.number)} className="mt-2 rounded bg-white/10 px-3 py-2 text-sm">제외 사유 기록</button>}
        </article>)}
        {data.status === 'direction_pending' && <button disabled={busy || data.results.some((r: any) => r.status === 'needs_review')} onClick={() => void action('approve_direction')} className="mt-3 rounded bg-indigo-600 px-3 py-2 text-sm">표시된 지침 승인 · AE 작업 시작</button>}
        {data.status === 'reviewed' && <p className="mt-3 text-sm text-green-400">검수가 완료되었습니다. 제출 버튼으로 최종 렌더링을 진행할 수 있습니다.</p>}
    </section>
}
