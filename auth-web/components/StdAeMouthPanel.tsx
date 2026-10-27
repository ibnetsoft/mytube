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
    const status: Record<string, string> = { complete:'최종 영상 저장 완료',needs_review:'후작업 보완 필요',not_started: '제출 후 시작', queued: '작업 대기', processing: '대사 판별·AE 처리 중', direction_pending: '씬별 작업 지침 승인 필요', direction_approved: 'AE 작업 대기', review_pending: '결과 검수 필요', reviewed: '검수 완료', failed: '작업 실패', obsolete: '원본 변경 · 다시 제출 필요' }
    const automaticRunning = data.automatic && (data.autoPending || data.status === 'processing')
    const automaticStatus: Record<string, string> = { direction:'실제 영상·대본 연출 확인 중',mouth_preparation:'화자 추적·입모양 소재 준비 및 검수 중',production:'AE 입모양·효과 합성 중',review:'씬 출력 검수 중',assembly:'자막·음향·장면 전환 최종 조립 중',final_review:'최종 영상 검수 중',auto_direction: '원본·연출 자동 검수 중', auto_review: 'AIR 결과 자동 검수 중', auto_enqueue: '최종 렌더 자동 등록 중' }
    return <section className="my-4 rounded-xl border border-white/15 p-4">
        <h3 className="font-semibold">{data.allParallax?'전체 씬 패럴럭스 · AE 영상 제작':data.postwork?'1~18씬 영상 후작업 · 입모양·반딧불·전환':'AIR 입모양 후작업 · 이미지와 대사 영상'}</h3>
        <p className="mt-2 text-sm text-gray-400">{data.allParallax?'검수된 분리 레이어를 AE에서 움직여 모든 씬을 영상으로 만들고, 대사 씬은 움직인 영상의 입을 추적해 후작업합니다.':'제출 후 실제 영상의 화자·입을 추적하고 대본에 근거한 효과를 AE로 합성합니다.'} 원본 영상 1배속과 확정 음성을 유지하며, 검수 통과 후 최종 영상까지 자동 저장합니다. 불확실한 씬은 보완 사유를 표시하고 멈춥니다.</p>
        <p className="mt-2 text-sm">{data.renderQueueId ? '최종 렌더 큐 등록 완료' : automaticRunning ? automaticStatus[data.phase] || 'AIR 자동 처리 대기·진행 중' : status[data.status] || data.status}</p>
        {(error || data.preparationError || data.error) && <p role="alert" className="mt-2 text-sm text-red-400">{error || data.preparationError || data.error}</p>}
        {!data.postwork && data.status === 'failed' && <button disabled={busy} onClick={() => void action('retry')} className="mt-2 rounded bg-white/10 px-3 py-2 text-sm">실패 작업 재시도</button>}
        {data.finalUrl&&<a href={data.finalUrl} target="_blank" rel="noopener noreferrer" className="mt-3 inline-block text-blue-300 underline">검수 완료된 최종 영상 보기</a>}
        {data.postwork&&data.status==='needs_review'&&<p className="mt-2 text-sm text-amber-200">표시된 원본·화자·연출을 보완한 뒤 프로젝트를 다시 열어 재제출하세요. 정상 제작된 소재와 음성은 보존됩니다.</p>}
        {data.results?.map((r: any) => <article key={r.number} className="mt-3 rounded border border-white/10 p-3">
            <p className="text-sm">{r.number}번 씬 · {r.speakers.join(', ') || '화자 없음'} · {r.status === 'approved' ? '승인 완료' : r.status === 'skipped' ? '입모양 제외' : r.status === 'needs_review' ? '화자·입 위치 검토 필요' : r.status === 'direction_pending' ? '지침 승인 대기' : '검수 대기'}</p>
            <p className="mt-1 text-sm text-gray-400">{r.reason || r.direction}</p>
            {r.videoUrl && <video className="mt-2 w-full max-w-2xl" controls preload="metadata" src={r.videoUrl} />}
            {!data.postwork && !automaticRunning && r.status === 'review_pending' && <button disabled={busy} onClick={() => void action('review', r.number)} className="mt-2 rounded bg-indigo-600 px-3 py-2 text-sm">입모양·AE 결과 승인</button>}
            {!data.postwork && data.status !== 'processing' && r.status === 'needs_review' && <button disabled={busy} onClick={() => void action('exclude', r.number)} className="mt-2 rounded bg-white/10 px-3 py-2 text-sm">제외 사유 기록</button>}
        </article>)}
        {!automaticRunning && data.status === 'direction_pending' && <button disabled={busy || data.results.some((r: any) => r.status === 'needs_review')} onClick={() => void action('approve_direction')} className="mt-3 rounded bg-indigo-600 px-3 py-2 text-sm">표시된 지침 승인 · AE 작업 시작</button>}
        {!data.automatic && data.status === 'reviewed' && <p className="mt-3 text-sm text-green-400">검수가 완료되었습니다. 제출 버튼으로 최종 렌더링을 진행할 수 있습니다.</p>}
    </section>
}
