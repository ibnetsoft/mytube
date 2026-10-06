'use client'
import { useCallback, useEffect, useState } from 'react'
import { authedFetch, useAuthToken } from '../referrals/_hooks'

const labels: Record<string, string> = { queued:'대기', processing:'작업 중', direction_pending:'지침 승인 대기', direction_approved:'AE 작업 대기', review_pending:'영상 완성 · 검수 대기', reviewed:'검수 완료', failed:'실패', obsolete:'원본 변경', skipped:'제외', needs_review:'확인 필요', approved:'결과 승인 완료' }
const group = (s: string) => ['review_pending','reviewed'].includes(s) ? 'done' : ['failed','obsolete'].includes(s) ? 'error' : s === 'processing' ? 'running' : 'queue'
export default function Page() {
    const { token, ready } = useAuthToken()
    const [jobs, setJobs] = useState<any[]>([]), [error, setError] = useState(''), [updated, setUpdated] = useState('')
    const [filter, setFilter] = useState('all'), [selected, setSelected] = useState('')
    const load = useCallback(async () => {
        if (!token) return
        try {
            const res = await authedFetch(token, '/api/admin/ae-worker')
            const body = await res.json()
            if (!res.ok) throw new Error(body.error || '조회 실패')
            setJobs(body.jobs); setUpdated(body.generatedAt); setError('')
        } catch (e: any) { setError(e.message || '조회 실패') }
    }, [token])
    useEffect(() => { void load(); const timer = setInterval(() => void load(), 15000); return () => clearInterval(timer) }, [load])
    if (!ready) return <main className="p-6">로그인 확인 중…</main>
    if (!token) return <main className="p-6">관리자 로그인이 필요합니다. <a href="/" className="underline">로그인으로 이동</a></main>
    const shown = jobs.filter(j => filter === 'all' || group(j.state) === filter)
    const detail = jobs.find(j => j.id === selected)
    return <main className="min-h-screen bg-[#10131b] p-6 text-white"><div className="mx-auto max-w-6xl space-y-5">
        <div className="flex items-center justify-between"><h1 className="text-2xl font-bold">AE 워커 작업 현황</h1><button onClick={() => void load()} className="rounded bg-blue-600 px-4 py-2">새로고침</button></div>
        <p className="text-sm text-gray-400">15초마다 자동 갱신합니다. 큐의 작업 상태를 표시하며, 컴퓨터의 온라인 여부와는 별개입니다. 영상 완성 후 검수·승인이 필요합니다.</p>
        <p className="text-xs text-gray-400">최근 조회: {updated ? new Date(updated).toLocaleString('ko-KR') : '조회 중'} · 최근 작업 100개와 활성 작업을 표시합니다.</p>
        {error && <p role="alert" className="text-red-300">{error}</p>}
        <div className="flex flex-wrap gap-2">{[['all','전체'],['queue','큐·승인 대기'],['running','작업 중'],['done','영상 완성·검수'],['error','오류']].map(([key,label]) => <button key={key} onClick={() => setFilter(key)} className={`rounded px-4 py-2 ${filter===key?'bg-blue-600':'bg-white/10'}`}>{label} {jobs.filter(j => key==='all'||group(j.state)===key).length}</button>)}</div>
        {!shown.length && <p className="rounded border border-white/10 p-5">표시할 작업이 없습니다.</p>}
        {shown.map(j => <button key={j.id} onClick={() => setSelected(j.id)} className={`block w-full rounded-xl border p-4 text-left ${selected===j.id?'border-blue-400':'border-white/15'}`}>
            <div className="flex flex-wrap justify-between gap-2"><strong>{j.title} {j.topicId ? `· 토픽 ${j.topicId}` : ''}</strong><span>{labels[j.state] || j.state}</span></div>
            <p className="mt-2">{j.phase==='render' ? `AE 영상 ${j.completed}/${j.target}씬 완성` : `대사·입 위치 분석 ${j.analyzed}/${j.total}씬`}</p>
            <progress className="mt-2 w-full" max={(j.phase==='render'?j.target:j.total)||1} value={j.phase==='render'?j.completed:j.analyzed} />
            <p className="mt-2 text-xs text-gray-400">등록 {new Date(j.createdAt).toLocaleString('ko-KR')} · 갱신 {new Date(j.updatedAt).toLocaleString('ko-KR')}</p>
            {j.error && <p className="mt-2 text-sm text-red-300">{j.error}</p>}
        </button>)}
        {detail && <section className="rounded-xl border border-white/20 p-4"><h2 className="text-lg font-semibold">{detail.title} · 씬별 작업 결과</h2><p className="mt-1 text-xs text-gray-400">작업 ID: {detail.id}</p>
            <div className="mt-3 space-y-2">{detail.results.map((r:any) => <article key={r.number} className="rounded bg-white/5 p-3"><p>{r.number}씬 · {labels[r.status] || r.status} · {r.speakers.join(', ') || '화자 없음'}</p><p className="mt-1 text-sm text-gray-400">{r.note}</p>{r.videoUrl && <a href={r.videoUrl} target="_blank" rel="noopener noreferrer" className="mt-2 inline-block text-blue-300 underline">완성 영상 보기</a>}</article>)}</div>
        </section>}
        <a href="/dashboard" className="inline-block text-blue-300 underline">관리자 화면으로 돌아가기</a>
    </div></main>
}
