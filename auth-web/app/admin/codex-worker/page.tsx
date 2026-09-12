'use client'

import { useCallback, useEffect, useMemo, useState } from 'react'
import { authedFetch, formatDate, useAuthToken } from '../referrals/_hooks'

type Worker = {
    worker_id: string
    worker_group: string
    online: boolean
    supports_codex: boolean
    supports_repair: boolean
    last_heartbeat_at: string | null
}
type Job = {
    id: string
    job_type: string
    status: string
    progress?: number
    message?: string
    error_message?: string
    topic_queue_id?: string
    flow?: 'new_generation' | 'repair'
    created_at?: string
}
type Topic = {
    id: string
    title: string
    category_name: string
    status: string
    assigned_at?: string | null
    language: string
    duration_minutes: number
    script_status: string
    structure_status: string
    scene_count: number
    image_count: number
    thumbnail_status: string
    thumbnail_url: string
    latest_job: Job | null
    repair_status?: string
    admin_hidden?: boolean
}
type DashboardData = {
    generated_at: string
    summary: {
        total_topics: number
        prepared_topics: number
        active_jobs: number
        failed_jobs: number
        thumbnails_completed: number
        repair_topics: number
        visible_user_topics: number
    }
    workers: Worker[]
    jobs: Job[]
    topics: Topic[]
    repair_topics: Topic[]
    visible_user_topics: Topic[]
}

const ACTIVE_STATUSES = ['pending', 'claimed', 'rendering', 'running']

const tone = (value: string) => {
    const normalized = String(value || '').toLowerCase()
    if (['completed', 'ready', 'online'].some(token => normalized.includes(token))) return 'bg-emerald-500/15 text-emerald-300 border-emerald-500/30'
    if (['failed', 'error', 'canceled', 'cancelled'].some(token => normalized.includes(token))) return 'bg-rose-500/15 text-rose-300 border-rose-500/30'
    if (['running', 'rendering', 'claimed', 'queued', 'pending', 'listed'].some(token => normalized.includes(token))) return 'bg-amber-500/15 text-amber-200 border-amber-500/30'
    return 'bg-slate-700/60 text-slate-300 border-slate-600'
}

export default function CodexWorkerAdminPage() {
    const { token, ready } = useAuthToken()
    const [data, setData] = useState<DashboardData | null>(null)
    const [loading, setLoading] = useState(true)
    const [error, setError] = useState('')
    const [notice, setNotice] = useState('')
    const [busy, setBusy] = useState('')
    const [query, setQuery] = useState('')
    const [hideConfirm, setHideConfirm] = useState(false)

    const refresh = useCallback(async () => {
        if (!token) return
        setLoading(true)
        try {
            const response = await authedFetch(token, '/api/admin/codex-worker', { cache: 'no-store' })
            const body = await response.json()
            if (!response.ok) throw new Error(body.error || '상태를 불러오지 못했습니다.')
            setData(body)
            setError('')
        } catch (err: any) {
            setError(err?.message || '상태를 불러오지 못했습니다.')
        } finally {
            setLoading(false)
        }
    }, [token])

    useEffect(() => { if (ready) void refresh() }, [ready, refresh])
    useEffect(() => {
        if (!token) return
        const timer = window.setInterval(() => void refresh(), 10_000)
        return () => window.clearInterval(timer)
    }, [token, refresh])

    const act = async (action: 'queue' | 'retry' | 'cancel', value: string) => {
        if (!token || busy) return
        setBusy(`${action}:${value}`)
        setNotice('')
        try {
            const body = action === 'queue' ? { action, topic_id: value } : { action, job_id: value }
            const response = await authedFetch(token, '/api/admin/codex-worker', { method: 'POST', body: JSON.stringify(body) })
            const result = await response.json()
            if (!response.ok) throw new Error(result.error || '작업 요청에 실패했습니다.')
            setNotice(action === 'queue' ? '신규 Codex 생성 작업을 큐에 넣었습니다.' : action === 'retry' ? '실패 작업을 다시 큐에 넣었습니다.' : '대기 작업을 취소했습니다.')
            await refresh()
        } catch (err: any) {
            setError(err?.message || '작업 요청에 실패했습니다.')
        } finally {
            setBusy('')
        }
    }

    const hideVisibleForRepair = async () => {
        if (!token || busy) return
        if (!hideConfirm) {
            setHideConfirm(true)
            return
        }
        setHideConfirm(false)
        setBusy('hide-visible-for-repair')
        setNotice('')
        try {
            const response = await authedFetch(token, '/api/admin/codex-worker', {
                method: 'POST',
                body: JSON.stringify({ action: 'hide-visible-for-repair' }),
            })
            const result = await response.json()
            if (!response.ok) throw new Error(result.error || '유저웹 토픽 가림에 실패했습니다.')
            setNotice(`${result.hidden_count || 0}개 토픽을 삭제하지 않고 리페어 목록으로 이동했습니다.`)
            await refresh()
        } catch (err: any) {
            setError(err?.message || '유저웹 토픽 가림에 실패했습니다.')
        } finally {
            setBusy('')
        }
    }

    const queueRepair = async (topic: Topic) => {
        if (!token || busy) return
        if (!topic.duration_minutes || !topic.scene_count) {
            setError(`토픽 #${topic.id}의 기존 분량 또는 씬 수를 확인할 수 없어 리페어를 큐잉하지 않았습니다.`)
            return
        }
        setBusy(`repair:${topic.id}`)
        setNotice('')
        try {
            const response = await authedFetch(token, '/api/admin/topics-queue/repair', {
                method: 'POST',
                body: JSON.stringify({
                    topicId: topic.id,
                    targetMinutes: topic.duration_minutes,
                    targetSceneCount: topic.scene_count,
                }),
            })
            const result = await response.json()
            if (!response.ok) throw new Error(result.error || '리페어 큐 등록에 실패했습니다.')
            setNotice(`토픽 #${topic.id} 리페어를 기존 ${topic.duration_minutes}분/${topic.scene_count}씬 기준으로 큐에 넣었습니다.`)
            await refresh()
        } catch (err: any) {
            setError(err?.message || '리페어 큐 등록에 실패했습니다.')
        } finally {
            setBusy('')
        }
    }

    const filterTopics = useCallback((items: Topic[]) => {
        const needle = query.trim().toLowerCase()
        return items.filter(topic => !needle || `${topic.id} ${topic.title} ${topic.category_name}`.toLowerCase().includes(needle))
    }, [query])
    const topics = useMemo(() => filterTopics(data?.topics || []), [data?.topics, filterTopics])
    const repairTopics = useMemo(() => filterTopics(data?.repair_topics || []), [data?.repair_topics, filterTopics])
    const codexWorkers = (data?.workers || []).filter(worker => worker.supports_codex || worker.supports_repair)

    return <main className="min-h-screen bg-[#0b111a] text-slate-100">
        <div className="mx-auto max-w-[1500px] px-4 py-7 sm:px-6">
            <div className="mb-7 flex flex-col gap-4 border-b border-slate-800 pb-6 lg:flex-row lg:items-end lg:justify-between">
                <div>
                    <p className="text-xs font-bold tracking-[0.2em] text-cyan-400">AIR STUDIO / ADMIN</p>
                    <h1 className="mt-2 text-3xl font-black tracking-tight">Codex 워커 운영 센터</h1>
                    <p className="mt-2 text-sm text-slate-400">신규 콘텐츠 생성과 기존 토픽 리페어를 서로 다른 큐 흐름으로 관리합니다.</p>
                </div>
                <div className="flex flex-wrap items-center gap-3">
                    <span className="text-xs text-slate-500">{data?.generated_at ? `갱신 ${formatDate(data.generated_at)}` : ''}</span>
                    <input value={query} onChange={event => setQuery(event.target.value)} placeholder="ID·제목·카테고리 검색" className="w-56 rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-xs outline-none focus:border-cyan-500" />
                    <button onClick={() => void refresh()} disabled={loading} className="rounded-lg border border-cyan-500/40 bg-cyan-500/10 px-4 py-2 text-sm font-bold text-cyan-200 disabled:opacity-50">{loading ? '불러오는 중…' : '새로고침'}</button>
                </div>
            </div>

            {error && <div className="mb-5 rounded-lg border border-rose-500/40 bg-rose-500/10 px-4 py-3 text-sm text-rose-200">{error}</div>}
            {notice && <div className="mb-5 rounded-lg border border-emerald-500/40 bg-emerald-500/10 px-4 py-3 text-sm text-emerald-200">{notice}</div>}

            <section className="grid gap-3 sm:grid-cols-2 xl:grid-cols-5">
                {[
                    ['신규 생성 대상', data?.topics.length ?? 0],
                    ['리페어 대기·진행', data?.summary.repair_topics ?? 0],
                    ['유저웹 노출 후보', data?.summary.visible_user_topics ?? 0],
                    ['실행 중 작업', data?.summary.active_jobs ?? 0],
                    ['실패 작업', data?.summary.failed_jobs ?? 0],
                ].map(([label, value]) => <div key={String(label)} className="rounded-xl border border-slate-800 bg-slate-900/70 p-4"><p className="text-xs text-slate-500">{label}</p><p className="mt-2 text-3xl font-black">{value}</p></div>)}
            </section>

            <section className="mt-6 rounded-xl border border-amber-500/30 bg-amber-500/5 p-5">
                <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
                    <div>
                        <h2 className="font-bold text-amber-100">유저웹 노출 관리</h2>
                        <p className="mt-1 text-xs leading-5 text-amber-200/70">가림은 삭제가 아닙니다. 미배정 pending 토픽만 excluded/admin_hidden으로 전환하며, 리페어가 끝나도 관리자 검수 전에는 자동 재노출하지 않습니다.</p>
                    </div>
                    <div className="flex items-center gap-2">
                        {hideConfirm && <button onClick={() => setHideConfirm(false)} disabled={Boolean(busy)} className="rounded border border-slate-600 px-3 py-2 text-xs text-slate-300 disabled:opacity-50">취소</button>}
                        <button onClick={() => void hideVisibleForRepair()} disabled={Boolean(busy) || (data?.summary.visible_user_topics ?? 0) === 0} className="rounded-lg border border-amber-400/40 bg-amber-500/15 px-4 py-2 text-sm font-bold text-amber-100 disabled:cursor-not-allowed disabled:opacity-40">
                            {busy === 'hide-visible-for-repair' ? '가림 처리 중…' : hideConfirm ? '현재 노출 후보 전체 가림 확정' : '유저웹 토픽 가림 및 리페어 대기'}
                        </button>
                    </div>
                </div>
            </section>

            <section className="mt-6 rounded-xl border border-slate-800 bg-slate-900/70 p-5">
                <div className="mb-4 flex items-center justify-between"><div><h2 className="font-bold">워커 상태</h2><p className="mt-1 text-xs text-slate-500">신규 생성: codex_content_generate · 기존 리페어: script_plan_generate 체인</p></div><span className="text-xs text-slate-500">하트비트 90초 기준</span></div>
                <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
                    {codexWorkers.map(worker => <div key={worker.worker_id} className="rounded-lg border border-slate-800 bg-slate-950/60 p-3"><div className="flex items-center justify-between gap-2"><span className="font-mono text-sm">{worker.worker_id}</span><span className={`rounded border px-2 py-0.5 text-[11px] font-bold ${tone(worker.online ? 'online' : 'offline')}`}>{worker.online ? 'ONLINE' : 'OFFLINE'}</span></div><p className="mt-2 text-xs text-slate-500">{worker.worker_group} · {formatDate(worker.last_heartbeat_at)}</p><p className="mt-2 text-[11px] text-slate-400">{worker.supports_codex ? '신규 생성' : ''}{worker.supports_codex && worker.supports_repair ? ' + ' : ''}{worker.supports_repair ? '기존 리페어' : ''}</p></div>)}
                    {codexWorkers.length === 0 && <p className="text-sm text-slate-500">Codex 생성 또는 리페어 작업을 허용한 워커가 등록되지 않았습니다.</p>}
                </div>
            </section>

            <section className="mt-6 rounded-xl border border-amber-500/20 bg-slate-900/70 p-5">
                <div className="mb-4"><h2 className="font-bold">기존 토픽 리페어 목록</h2><p className="mt-1 text-xs text-slate-500">excluded/admin_hidden 상태를 유지한 채 기존 분량과 씬 구조를 기준으로 보정합니다. 검수 후 별도 가림 해제해야 유저웹에 노출됩니다.</p></div>
                <div className="overflow-x-auto"><table className="min-w-[980px] w-full text-left text-xs"><thead className="border-b border-slate-800 text-slate-500"><tr><th className="p-3">토픽</th><th className="p-3">기존 기준</th><th className="p-3">자료 상태</th><th className="p-3">리페어 상태</th><th className="p-3 text-right">작업</th></tr></thead><tbody>{repairTopics.map(topic => { const job = topic.latest_job; const active = Boolean(job && ACTIVE_STATUSES.includes(String(job.status).toLowerCase())); return <tr key={topic.id} className="border-b border-slate-800/80 align-top"><td className="p-3"><p className="font-semibold text-slate-100">{topic.title}</p><p className="mt-1 text-slate-500">#{topic.id} · {topic.category_name} · {topic.language}</p></td><td className="p-3 text-slate-300">{topic.duration_minutes || '-'}분 · {topic.scene_count || '-'}씬</td><td className="p-3"><p>대본 <span className={`rounded border px-1.5 py-0.5 ${tone(topic.script_status)}`}>{topic.script_status}</span></p><p className="mt-2 text-slate-400">이미지 {topic.image_count}/{topic.scene_count || '-'}</p></td><td className="p-3"><span className={`rounded border px-2 py-1 ${tone(topic.repair_status || 'listed')}`}>{topic.repair_status || 'listed'}</span>{job && <p className="mt-2 max-w-72 truncate text-slate-500">{job.job_type} · {job.status} · {job.message || job.error_message || '-'}</p>}</td><td className="p-3 text-right"><button onClick={() => void queueRepair(topic)} disabled={Boolean(busy) || active || !topic.duration_minutes || !topic.scene_count} className="rounded bg-amber-600 px-3 py-1.5 font-bold text-white disabled:cursor-not-allowed disabled:opacity-40">{busy === `repair:${topic.id}` ? '요청 중…' : active ? '리페어 진행 중' : '리페어 큐잉'}</button></td></tr>})}{repairTopics.length === 0 && <tr><td colSpan={5} className="p-8 text-center text-slate-500">리페어 목록이 없습니다.</td></tr>}</tbody></table></div>
            </section>

            <section className="mt-6 rounded-xl border border-cyan-500/20 bg-slate-900/70 p-5">
                <div className="mb-4"><h2 className="font-bold">신규 토픽 Codex 생성</h2><p className="mt-1 text-xs text-slate-500">신규 제작만 codex_content_generate 작업으로 큐잉합니다. 기존 토픽 보정에는 이 버튼을 사용하지 않습니다.</p></div>
                <div className="overflow-x-auto"><table className="min-w-[1100px] w-full text-left text-xs"><thead className="border-b border-slate-800 text-slate-500"><tr><th className="p-3">토픽</th><th className="p-3">대본 / 씬</th><th className="p-3">이미지</th><th className="p-3">썸네일</th><th className="p-3">최근 신규 생성 작업</th><th className="p-3 text-right">작업</th></tr></thead><tbody>{topics.map(topic => { const job = topic.latest_job; const state = String(job?.status || ''); const canRetry = ['failed','error','canceled','cancelled'].includes(state.toLowerCase()); const canCancel = state.toLowerCase() === 'pending'; const canQueue = String(topic.status || '').toLowerCase() === 'pending'; return <tr key={topic.id} className="border-b border-slate-800/80 align-top"><td className="p-3"><p className="font-semibold text-slate-100">{topic.title}</p><p className="mt-1 text-slate-500">#{topic.id} · {topic.category_name} · {topic.language}</p></td><td className="p-3"><span className={`rounded border px-2 py-1 ${tone(topic.script_status)}`}>{topic.script_status}</span><p className="mt-2 text-slate-400">{topic.scene_count}씬 · {topic.duration_minutes || '-'}분</p></td><td className="p-3 text-slate-300">{topic.image_count}/{topic.scene_count || '-'}</td><td className="p-3"><span className={`rounded border px-2 py-1 ${tone(topic.thumbnail_status)}`}>{topic.thumbnail_status}</span>{topic.thumbnail_url && <a href={topic.thumbnail_url} target="_blank" rel="noreferrer" className="mt-2 block text-cyan-400 hover:underline">배경 보기</a>}</td><td className="p-3">{job ? <><span className={`rounded border px-2 py-1 ${tone(state)}`}>{state}</span><p className="mt-2 max-w-64 truncate text-slate-400">{job.progress ?? 0}% · {job.message || job.error_message || '-'}</p></> : <span className="text-slate-600">기록 없음</span>}</td><td className="p-3 text-right"><div className="flex justify-end gap-2">{canRetry && <button onClick={() => void act('retry', job!.id)} disabled={Boolean(busy)} className="rounded border border-amber-500/40 px-2 py-1 text-amber-200 disabled:opacity-50">재시도</button>}{canCancel && <button onClick={() => void act('cancel', job!.id)} disabled={Boolean(busy)} className="rounded border border-rose-500/40 px-2 py-1 text-rose-200 disabled:opacity-50">취소</button>}<button onClick={() => void act('queue', topic.id)} disabled={Boolean(busy) || !canQueue || Boolean(job && ACTIVE_STATUSES.includes(state.toLowerCase()))} className="rounded bg-cyan-600 px-2 py-1 font-bold text-white disabled:cursor-not-allowed disabled:opacity-40">{busy === `queue:${topic.id}` ? '요청 중…' : '신규 Codex 생성'}</button></div></td></tr>})}{topics.length === 0 && <tr><td colSpan={6} className="p-8 text-center text-slate-500">표시할 신규 생성 토픽이 없습니다.</td></tr>}</tbody></table></div>
            </section>

            <section className="mt-6 rounded-xl border border-slate-800 bg-slate-900/70 p-5"><h2 className="font-bold">최근 작업 로그</h2><div className="mt-4 space-y-2">{(data?.jobs || []).slice(0, 20).map(job => <div key={job.id} className="flex flex-col gap-2 rounded-lg border border-slate-800 bg-slate-950/50 px-3 py-3 md:flex-row md:items-center"><span className={`w-fit rounded border px-2 py-1 text-[11px] font-bold ${tone(job.status)}`}>{job.status}</span><span className="rounded bg-slate-800 px-2 py-1 text-[11px] text-slate-300">{job.flow === 'repair' ? '기존 리페어' : '신규 생성'}</span><span className="font-mono text-xs text-slate-400">{job.id.slice(0, 8)}</span><span className="text-xs text-slate-300">토픽 #{job.topic_queue_id || '-'}</span><span className="flex-1 truncate text-xs text-slate-500">{job.message || job.error_message || '-'}</span><span className="text-xs text-slate-600">{formatDate(job.created_at)}</span></div>)}{!(data?.jobs || []).length && <p className="text-sm text-slate-500">추적 중인 작업 이력이 없습니다.</p>}</div></section>
        </div>
    </main>
}
