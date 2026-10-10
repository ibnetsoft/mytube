'use client'

import { useCallback, useEffect, useMemo, useRef, useState } from 'react'

type Topic = {
    id: string | number
    topic: string
    category_id: string | number
    category_name: string
    video_type: string
    status: string
    delete_block_reason?: string | null
}
type Props = {
    adminFetch: (input: RequestInfo | URL, init?: RequestInit) => Promise<Response>
    initialLanguage: 'ko' | 'ja' | 'en'
    onClose: () => void
    onDeleted: (ids: string[]) => void
}
const countries = { ko: '한국', ja: '일본', en: '미국' }
const PAGE_SIZE = 50
const MAX_SELECTION = 500
const canDelete = (topic: Topic) => ['pending', 'excluded'].includes(topic.status) && !topic.delete_block_reason

export default function AdminTopicDeleteDialog({ adminFetch, initialLanguage, onClose, onDeleted }: Props) {
    const [topics, setTopics] = useState<Topic[]>([])
    const [loading, setLoading] = useState(true)
    const [deleting, setDeleting] = useState(false)
    const [error, setError] = useState('')
    const [result, setResult] = useState('')
    const [category, setCategory] = useState('all')
    const [status, setStatus] = useState('all')
    const [videoType, setVideoType] = useState('all')
    const [search, setSearch] = useState('')
    const [page, setPage] = useState(1)
    const [selected, setSelected] = useState<Set<string>>(() => new Set())
    const [confirmation, setConfirmation] = useState<Topic[] | null>(null)
    const dialogRef = useRef<HTMLDivElement>(null)
    const mutationRef = useRef(false)
    const mountedRef = useRef(true)
    const loadControllerRef = useRef<AbortController | null>(null)

    const loadTopics = useCallback(async () => {
        loadControllerRef.current?.abort()
        const controller = new AbortController()
        loadControllerRef.current = controller
        setLoading(true)
        setError('')
        setSelected(new Set())
        setConfirmation(null)
        try {
            const rows: Topic[] = []
            let nextPage = 1
            while (true) {
                const params = new URLSearchParams({ language: initialLanguage, page: String(nextPage), perPage: '500' })
                const response = await adminFetch(`/api/admin/topics-queue/bulk-delete?${params}`, { cache: 'no-store', signal: controller.signal })
                const body = await response.json()
                if (!response.ok || body.success !== true || !Array.isArray(body.topics)) throw new Error(body.error || '토픽 목록을 불러오지 못했습니다.')
                if (controller.signal.aborted) return
                rows.push(...body.topics)
                if (!body.hasMore) break
                if (!body.topics.length || nextPage >= 200) throw new Error('토픽 목록을 모두 불러오지 못했습니다. 새로고침해 주세요.')
                nextPage++
            }
            setTopics([...new Map(rows.map(topic => [String(topic.id), topic])).values()])
            setPage(1)
        } catch (err) {
            if (!controller.signal.aborted) setError(err instanceof Error ? err.message : '토픽 목록을 불러오지 못했습니다.')
        } finally {
            if (!controller.signal.aborted) setLoading(false)
        }
    }, [adminFetch, initialLanguage])

    useEffect(() => {
        mountedRef.current = true
        void loadTopics()
        return () => { mountedRef.current = false; loadControllerRef.current?.abort() }
    }, [loadTopics])

    useEffect(() => {
        const previousFocus = document.activeElement as HTMLElement | null
        const previousOverflow = document.body.style.overflow
        document.body.style.overflow = 'hidden'
        dialogRef.current?.focus()
        return () => { document.body.style.overflow = previousOverflow; previousFocus?.focus() }
    }, [])

    useEffect(() => { dialogRef.current?.focus() }, [confirmation])

    const categories = useMemo(() => [...new Map(topics.map(topic => [String(topic.category_id), topic.category_name])).entries()]
        .sort((a, b) => a[1].localeCompare(b[1], 'ko')), [topics])
    const filtered = useMemo(() => topics.filter(topic =>
        (category === 'all' || String(topic.category_id) === category)
        && (status === 'all' || topic.status === status)
        && (videoType === 'all' || topic.video_type === videoType)
        && `${topic.id} ${topic.topic} ${topic.category_name}`.toLocaleLowerCase().includes(search.trim().toLocaleLowerCase())),
    [topics, category, status, videoType, search])
    const eligible = filtered.filter(canDelete)
    const totalPages = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE))
    const currentPage = Math.min(page, totalPages)
    const visible = filtered.slice((currentPage - 1) * PAGE_SIZE, currentPage * PAGE_SIZE)
    const selectedTopics = topics.filter(topic => selected.has(String(topic.id)) && canDelete(topic))
    const resetSelection = () => { setSelected(new Set()); setPage(1); setConfirmation(null); setResult('') }
    const toggle = (id: string) => setSelected(previous => {
        const next = new Set(previous)
        if (next.has(id)) next.delete(id)
        else if (next.size < MAX_SELECTION) next.add(id)
        return next
    })

    const deleteSelected = async () => {
        if (mutationRef.current || !confirmation?.length) return
        const ids = confirmation.map(topic => String(topic.id))
        mutationRef.current = true
        setDeleting(true)
        setError('')
        setResult('')
        try {
            const response = await adminFetch('/api/admin/topics-queue/bulk-delete', {
                method: 'DELETE', headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ ids, language: initialLanguage }),
            })
            const body = await response.json()
            if (!response.ok || body.success !== true || !Array.isArray(body.deletedIds)) throw new Error(body.error || '토픽을 삭제하지 못했습니다.')
            const deletedIds = body.deletedIds.map(String).filter((id: string) => ids.includes(id))
            const deletedSet = new Set(deletedIds)
            const skipped: Array<{ id: string; reason: string }> = Array.isArray(body.skipped) ? body.skipped : []
            if (deletedIds.length) onDeleted(deletedIds)
            if (!mountedRef.current) return
            setTopics(previous => previous.filter(topic => !deletedSet.has(String(topic.id))).map(topic => {
                const skippedItem = skipped.find(item => String(item.id) === String(topic.id))
                return skippedItem ? { ...topic, delete_block_reason: skippedItem.reason } : topic
            }))
            setSelected(new Set())
            setConfirmation(null)
            setResult(`${deletedIds.length}개 토픽을 삭제했습니다.${skipped.length ? ` ${skipped.length}개는 삭제되지 않았습니다. 목록의 사유를 확인해 주세요.` : ''}`)
        } catch (err) {
            if (mountedRef.current) setError(err instanceof Error ? err.message : '삭제 결과를 확인하지 못했습니다. 목록을 새로고침해 주세요.')
        } finally {
            mutationRef.current = false
            if (mountedRef.current) setDeleting(false)
        }
    }

    return (
        <div className="fixed inset-0 z-[100] flex items-center justify-center bg-black/80 p-3 sm:p-6">
            <div ref={dialogRef} role="dialog" aria-modal="true" aria-labelledby="topic-delete-title" tabIndex={-1}
                onKeyDown={event => {
                    if (event.key === 'Escape') { event.stopPropagation(); if (!deleting) confirmation ? setConfirmation(null) : onClose() }
                    if (event.key === 'Tab') {
                        const elements = Array.from(dialogRef.current?.querySelectorAll<HTMLElement>('button:not(:disabled), input:not(:disabled), select:not(:disabled), [tabindex="0"]') || [])
                        const first = elements[0], last = elements.at(-1)
                        if (event.shiftKey && (document.activeElement === first || document.activeElement === dialogRef.current)) { event.preventDefault(); last?.focus() }
                        else if (!event.shiftKey && (document.activeElement === last || document.activeElement === dialogRef.current)) { event.preventDefault(); first?.focus() }
                    }
                }}
                className="flex max-h-[90dvh] w-full max-w-5xl flex-col overflow-hidden rounded-2xl border border-white/15 bg-[#111827] text-gray-100 shadow-2xl outline-none">
                <div className="flex items-start justify-between gap-4 border-b border-white/10 p-5">
                    <div>
                        <h2 id="topic-delete-title" className="text-lg font-black">{countries[initialLanguage]} 토픽 선택 삭제</h2>
                        <p className="mt-2 text-sm text-gray-400">모든 카테고리의 대기·준비·가림 토픽을 관리합니다. 작업이 연결된 토픽은 보호됩니다.</p>
                    </div>
                    <button type="button" disabled={deleting} onClick={onClose} className="shrink-0 rounded-lg border border-white/15 px-3 py-2 text-sm disabled:opacity-40">닫기</button>
                </div>

                {error && <p role="alert" className="mx-5 mt-4 rounded-lg border border-red-400/30 bg-red-500/10 p-3 text-sm text-red-200">{error}</p>}
                {result && <p role="status" className="mx-5 mt-4 rounded-lg border border-emerald-400/30 bg-emerald-500/10 p-3 text-sm text-emerald-200">{result}</p>}

                {confirmation ? (
                    <>
                        <div className="min-h-0 flex-1 overflow-y-auto p-5">
                            <h3 className="font-bold text-red-200">선택한 {confirmation.length}개 토픽을 삭제할까요?</h3>
                            <p className="mt-2 text-sm text-gray-300">삭제 후에는 되돌릴 수 없습니다. 아래 토픽만 삭제합니다.</p>
                            <ul className="mt-4 divide-y divide-white/10 rounded-xl border border-white/10 px-4">
                                {confirmation.map(topic => <li key={topic.id} className="py-3 text-sm"><span className="mr-2 text-gray-400">#{topic.id} · {topic.category_name}</span>{topic.topic}</li>)}
                            </ul>
                        </div>
                        <div className="flex justify-end gap-3 border-t border-white/10 p-5">
                            <button type="button" disabled={deleting} onClick={() => setConfirmation(null)} className="rounded-lg border border-white/15 px-4 py-2 disabled:opacity-40">돌아가기</button>
                            <button type="button" disabled={deleting} onClick={() => void deleteSelected()} className="rounded-lg bg-red-600 px-4 py-2 font-bold hover:bg-red-500 disabled:opacity-40">{deleting ? '삭제 중…' : '삭제 확정'}</button>
                        </div>
                    </>
                ) : (
                    <>
                        <div className="grid grid-cols-2 gap-3 p-4 sm:p-5 lg:grid-cols-4 [&>label]:min-w-0">
                            <label className="text-xs text-gray-400">카테고리<select aria-label="카테고리" disabled={loading} value={category} onChange={e => { setCategory(e.target.value); resetSelection() }} className="mt-1 block w-full rounded-lg border border-white/15 bg-[#0b1220] p-2.5 text-sm text-white"><option value="all">전체 카테고리</option>{categories.map(([id, name]) => <option key={id} value={id}>{name}</option>)}</select></label>
                            <label className="text-xs text-gray-400">상태<select aria-label="상태" disabled={loading} value={status} onChange={e => { setStatus(e.target.value); resetSelection() }} className="mt-1 block w-full rounded-lg border border-white/15 bg-[#0b1220] p-2.5 text-sm text-white"><option value="all">전체 상태</option><option value="pending">대기·준비</option><option value="excluded">가림</option></select></label>
                            <label className="text-xs text-gray-400">영상 유형<select aria-label="영상 유형" disabled={loading} value={videoType} onChange={e => { setVideoType(e.target.value); resetSelection() }} className="mt-1 block w-full rounded-lg border border-white/15 bg-[#0b1220] p-2.5 text-sm text-white"><option value="all">전체 유형</option><option value="longform">롱폼</option><option value="shorts">쇼츠</option></select></label>
                            <label className="text-xs text-gray-400">토픽 검색<input aria-label="토픽 검색" type="search" value={search} disabled={loading} onChange={e => { setSearch(e.target.value); resetSelection() }} placeholder="제목, 번호, 카테고리" className="mt-1 block w-full rounded-lg border border-white/15 bg-[#0b1220] p-2.5 text-sm text-white" /></label>
                        </div>
                        <div className="flex flex-wrap items-center gap-3 border-y border-white/10 px-5 py-3 text-sm">
                            <span>검색 결과 {filtered.length}개 · 선택 {selected.size}개</span>
                            <button type="button" disabled={loading || !eligible.length || eligible.length > MAX_SELECTION} onClick={() => setSelected(new Set(eligible.map(topic => String(topic.id))))} className="rounded-lg border border-blue-400/30 px-3 py-1.5 text-blue-200 disabled:opacity-40">검색 결과 전체 선택</button>
                            <button type="button" disabled={!selected.size} onClick={() => setSelected(new Set())} className="text-gray-300 disabled:opacity-40">선택 해제</button>
                            <button type="button" disabled={loading} onClick={() => { setResult(''); void loadTopics() }} className="ml-auto text-gray-300 disabled:opacity-40">목록 새로고침</button>
                            {eligible.length > MAX_SELECTION && <p className="w-full text-xs text-amber-200">한 번에 최대 500개를 삭제할 수 있습니다. 검색이나 필터로 범위를 좁혀 주세요.</p>}
                        </div>
                        <div className="min-h-0 flex-1 overflow-auto">
                            {loading ? <p role="status" className="p-10 text-center text-gray-400">전체 카테고리의 토픽을 불러오는 중…</p> : (
                                <table className="w-full text-left text-sm">
                                    <thead className="sticky top-0 bg-[#172033] text-xs text-gray-400"><tr><th className="px-4 py-3">선택</th><th className="px-3 py-3">카테고리</th><th className="px-3 py-3">토픽</th><th className="px-4 py-3">상태</th></tr></thead>
                                    <tbody className="divide-y divide-white/10">{visible.map(topic => (
                                        <tr key={topic.id} className={selected.has(String(topic.id)) ? 'bg-blue-500/10' : ''}>
                                            <td className="px-4 py-3"><input type="checkbox" aria-label={`토픽 ${topic.id} 선택`} checked={selected.has(String(topic.id))} disabled={!canDelete(topic) || (selected.size >= MAX_SELECTION && !selected.has(String(topic.id)))} onChange={() => toggle(String(topic.id))} className="h-4 w-4 accent-blue-500" /></td>
                                            <td className="px-3 py-3 text-gray-300">{topic.category_name}<span className="mt-1 block text-xs text-gray-500">{topic.video_type === 'shorts' ? '쇼츠' : '롱폼'}</span></td>
                                            <td className="min-w-[180px] px-3 py-3"><span className="mr-2 text-xs text-gray-500">#{topic.id}</span>{topic.topic}{topic.delete_block_reason && <p className="mt-1 text-xs text-amber-200">{topic.delete_block_reason}</p>}</td>
                                            <td className="whitespace-nowrap px-4 py-3 text-gray-300">{topic.status === 'excluded' ? '가림' : '대기·준비'}</td>
                                        </tr>
                                    ))}</tbody>
                                </table>
                            )}
                            {!loading && !filtered.length && <p className="p-10 text-center text-gray-400">표시할 토픽이 없습니다.</p>}
                        </div>
                        <div className="flex flex-wrap items-center justify-between gap-3 border-t border-white/10 p-5">
                            <div className="flex items-center gap-3 text-sm"><button type="button" disabled={loading || currentPage <= 1} onClick={() => setPage(currentPage - 1)} className="rounded-lg border border-white/15 px-3 py-2 disabled:opacity-40">이전</button><span>{currentPage} / {totalPages}</span><button type="button" disabled={loading || currentPage >= totalPages} onClick={() => setPage(currentPage + 1)} className="rounded-lg border border-white/15 px-3 py-2 disabled:opacity-40">다음</button></div>
                            <button type="button" disabled={loading || !selectedTopics.length} onClick={() => { setError(''); setConfirmation(selectedTopics) }} className="rounded-lg bg-red-600 px-4 py-2 font-bold hover:bg-red-500 disabled:opacity-40">선택 {selectedTopics.length}개 삭제</button>
                        </div>
                    </>
                )}
            </div>
        </div>
    )
}
