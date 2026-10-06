'use client'

import { useEffect, useState } from 'react'

const labels: Record<string, string> = {
    not_started: '제출 후 시작', queued: '작업 대기', processing: '대사 분석·AE 생성 중',
    direction_pending: 'Codex 지침 검토 대기', direction_approved: 'AE 생성 대기',
    review_pending: 'Codex 결과 검수 중', reviewed: 'AE 검수 완료',
    failed: '작업 오류', obsolete: '입력 변경으로 재확인 필요',
    direction_approved_scene: 'AE 생성 대기', direction_pending_scene: '지침 작성 완료',
    approved: '검수 완료', skipped: '효과 제외', needs_review: '추가 확인 필요',
}

export default function StdAeProgress({ projectId, headers }: { projectId: string; headers: Record<string, string> }) {
    const [open, setOpen] = useState(false)
    const [data, setData] = useState<any>(null)
    const [error, setError] = useState('')
    const [updated, setUpdated] = useState('')
    const [refresh, setRefresh] = useState(0)
    const authorization = headers.Authorization
    const impersonate = headers['x-impersonate-email']
    useEffect(() => { setData(null); setUpdated(''); setError('') }, [projectId])
    useEffect(() => {
        if (!open) return
        const controller = new AbortController()
        let timer: ReturnType<typeof setTimeout>
        const load = async () => {
            try {
                const response = await fetch(`/api/std/projects/${encodeURIComponent(projectId)}/ae-mouth`, {
                    headers: { Authorization: authorization, ...(impersonate ? { 'x-impersonate-email': impersonate } : {}) },
                    cache: 'no-store', signal: controller.signal,
                })
                const body = await response.json()
                if (!response.ok) throw new Error(body.error || '진행 상태 조회 실패')
                if (controller.signal.aborted) return
                setData(body); setError(''); setUpdated(new Date().toLocaleTimeString('ko-KR'))
            } catch (e: any) {
                if (!controller.signal.aborted) setError(e.message || '진행 상태 조회 실패')
            } finally {
                if (!controller.signal.aborted) timer = setTimeout(load, 15000)
            }
        }
        void load()
        return () => { controller.abort(); clearTimeout(timer) }
    }, [projectId, authorization, impersonate, open, refresh])
    const results: any[] = data?.results || []
    const complete = results.filter(row => ['approved', 'skipped'].includes(row.status)).length
    return <aside className="fixed bottom-4 right-4 z-[60] w-[min(380px,calc(100vw-32px))]">
        {open && <section id="ae-progress-details" className="mb-2 max-h-[65vh] overflow-y-auto rounded-xl border border-cyan-500/30 bg-[#101820] p-4 text-white shadow-2xl">
            <div className="flex items-center justify-between"><h3 className="font-bold">AE 작업 진행 현황</h3><button type="button" onClick={() => setRefresh(value => value + 1)} className="text-xs text-cyan-300">새로고침</button></div>
            <p role="status" className="mt-3 text-sm text-cyan-200">{data ? data.applicable ? labels[data.status] || data.status : '이 프로젝트는 AE 입모양 작업 대상이 아닙니다.' : '작업 상태 확인 중...'}</p>
            {data?.applicable && <p className="mt-2 text-xs text-gray-400">Codex가 지침과 결과를 검수하고 다음 작업으로 이어갑니다.</p>}
            {results.length > 0 && <p className="mt-2 text-xs">검수 완료·제외 {complete}개 / 분석 결과 {results.length}개</p>}
            {(error || data?.error || data?.preparationError) && <p role="alert" className="mt-3 text-xs text-red-300">{error || data.error || data.preparationError}</p>}
            {results.map(row => <div key={row.number} className="mt-2 rounded bg-white/5 p-2 text-xs">
                <p>{row.number}번 씬 · {labels[row.status + '_scene'] || labels[row.status] || row.status}</p>
                {row.speakers?.length > 0 && <p className="mt-1 text-gray-400">{row.speakers.join(', ')}</p>}
                {row.reason && <p className="mt-1 text-gray-400">{row.reason}</p>}
            </div>)}
            <p className="mt-3 text-[11px] text-gray-500">15초마다 갱신{updated ? ` · 마지막 확인 ${updated}` : ''}</p>
        </section>}
        <button type="button" aria-expanded={open} aria-controls="ae-progress-details" onClick={() => setOpen(value => !value)} className="ml-auto block rounded-lg border border-cyan-500/40 bg-[#10252d] px-4 py-2 text-sm font-bold text-cyan-200 shadow-lg">{open ? 'AE 상태 닫기' : 'AE 작업 상태'}</button>
    </aside>
}
