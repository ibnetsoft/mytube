'use client'

import { useEffect, useRef, useState } from 'react'
import type { SupportedLocale } from '@/lib/i18n'
import { stdUiText } from '@/lib/stdUiText'

export type TopicProjectRow = { id: string; title: string; thumbnail: string; steps: boolean[]; submitted?: boolean }
const PAGE_SIZE = 10
const stages = ['주제', '기획', '대본', '이미지', 'TTS', '자막', '썸네일']
type ProjectTab = 'unfinished' | 'submitted'

export default function TopicProjectDialog({ rows, activeId, locale, onClose, onSelect }: {
    rows: TopicProjectRow[]; activeId?: string; locale: SupportedLocale;
    onClose: () => void; onSelect: (id: string) => Promise<boolean>;
}) {
    const dialog = useRef<HTMLDialogElement>(null)
    const [query, setQuery] = useState('')
    const [page, setPage] = useState(0)
    const [tab, setTab] = useState<ProjectTab>('unfinished')
    const [opening, setOpening] = useState('')
    const [failed, setFailed] = useState(false)
    const ui = (text: string) => stdUiText(locale, text)
    const unfinishedCount = rows.filter(row => !row.submitted).length
    const submittedCount = rows.length - unfinishedCount
    const filtered = rows
        .filter(row => tab === 'submitted' ? row.submitted : !row.submitted)
        .filter(row => row.title.toLocaleLowerCase().includes(query.trim().toLocaleLowerCase()))
        .sort((a, b) => Number(b.id === activeId) - Number(a.id === activeId))
    const pageCount = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE))
    const currentPage = Math.min(page, pageCount - 1)
    const visible = filtered.slice(currentPage * PAGE_SIZE, (currentPage + 1) * PAGE_SIZE)
    useEffect(() => {
        const previous = document.activeElement as HTMLElement | null
        const modal = dialog.current
        modal?.showModal()
        return () => { modal?.close(); previous?.focus() }
    }, [])
    const choose = async (id: string) => {
        if (opening) return
        if (id === activeId) { onClose(); return }
        setOpening(id); setFailed(false)
        try { if (await onSelect(id)) onClose(); else setFailed(true) }
        catch { setFailed(true) }
        finally { setOpening('') }
    }
    return <dialog ref={dialog} aria-labelledby="topic-project-title" onCancel={event => { event.preventDefault(); if (!opening) onClose() }}
        className="m-auto w-[min(1200px,96vw)] max-w-none overflow-hidden rounded-2xl border border-white/15 bg-[#161a22] p-0 text-gray-200 shadow-2xl backdrop:bg-black/75">
        <div className="flex max-h-[88dvh] flex-col">
            <header className="flex items-center justify-between gap-4 border-b border-white/10 px-5 py-4">
                <h2 id="topic-project-title" className="text-lg font-bold">{ui('토픽')} · {ui('프로젝트 선택')}</h2>
                <button type="button" disabled={!!opening} onClick={onClose} className="rounded border border-white/15 px-3 py-1.5 text-sm disabled:opacity-40">{ui('닫기')}</button>
            </header>
            <div className="space-y-3 px-5 py-3">
                <div className="inline-flex rounded-lg border border-white/15 bg-black/20 p-1 text-xs font-bold">
                    {[
                        { id: 'unfinished' as const, label: ui('미완성'), count: unfinishedCount },
                        { id: 'submitted' as const, label: ui('제출 완료'), count: submittedCount },
                    ].map(item => (
                        <button key={item.id} type="button" disabled={!!opening} onClick={() => { setTab(item.id); setPage(0) }}
                            className={`rounded-md px-3 py-1.5 transition ${tab === item.id ? 'bg-blue-500 text-white' : 'text-gray-400 hover:bg-white/10 hover:text-gray-100'} disabled:opacity-40`}>
                            {item.label} <span className="ml-1 opacity-80">{item.count}</span>
                        </button>
                    ))}
                </div>
                <input autoFocus value={query} onChange={e => { setQuery(e.target.value); setPage(0) }} aria-label={ui('영상 제목 검색')} placeholder={ui('영상 제목 검색')}
                    className="w-full rounded-lg border border-white/15 bg-black/20 px-3 py-2 text-sm outline-none focus:border-blue-400" />
            </div>
            <div className="min-h-0 overflow-auto px-5" aria-busy={!!opening}>
                <table className="w-full min-w-[720px] border-collapse text-sm">
                    <thead className="sticky top-0 bg-[#202632] text-xs text-gray-400"><tr>
                        <th className="p-3">{ui('썸네일')}</th><th className="p-3 text-left">{ui('영상 제목')}</th>
                        {stages.map(stage => <th key={stage} className="whitespace-nowrap px-2 py-3">{ui(stage)}</th>)}
                    </tr></thead>
                    <tbody>{visible.map(row => <tr key={row.id} className={`border-b border-white/5 ${row.id === activeId ? 'bg-blue-500/15' : 'hover:bg-white/5'}`}>
                        <td className="w-28 p-2"><button type="button" disabled={!!opening} aria-label={row.title} onClick={() => void choose(row.id)} className="block w-24 overflow-hidden rounded border border-white/10">
                            {row.thumbnail ? <img src={row.thumbnail} alt="" className="aspect-video w-full object-cover" onError={e => { e.currentTarget.style.visibility = 'hidden' }} /> : <span className="flex aspect-video items-center justify-center bg-black/20 text-gray-500">—</span>}
                        </button></td>
                        <td className="p-3"><button type="button" disabled={!!opening} onClick={() => void choose(row.id)} className="w-full text-left font-medium leading-6 hover:text-blue-300 disabled:opacity-60">
                            {row.title}{row.id === activeId && <span className="ml-2 whitespace-nowrap text-xs text-blue-300">{ui('선택됨')}</span>}
                            {opening === row.id && <span className="ml-2 text-xs text-cyan-300">{ui('불러오는 중…')}</span>}
                        </button></td>
                        {stages.map((stage, i) => <td key={stage} className="px-2 text-center"><span role="img" aria-label={`${ui(stage)}: ${ui(row.steps[i] ? '완료' : '미완료')}`} title={ui(row.steps[i] ? '완료' : '미완료')} className={row.steps[i] ? 'text-emerald-500' : 'text-gray-600'}>{row.steps[i] ? '●' : '○'}</span></td>)}
                    </tr>)}</tbody>
                </table>
                {!visible.length && <p className="py-12 text-center text-gray-400">{ui('검색 결과가 없습니다.')}</p>}
            </div>
            {failed && <p role="alert" className="px-5 pt-3 text-sm text-red-300">{ui('프로젝트를 불러오지 못했습니다. 다시 시도해 주세요.')}</p>}
            <footer className="flex items-center justify-between gap-3 border-t border-white/10 px-5 py-4 text-sm">
                <span>{filtered.length} {ui('개')}</span>
                <nav aria-label={ui('페이지 이동')} className="flex items-center gap-3">
                    <button type="button" disabled={currentPage === 0 || !!opening} onClick={() => setPage(currentPage - 1)} className="rounded border border-white/15 px-3 py-1.5 disabled:opacity-30">{ui('이전')}</button>
                    <span aria-live="polite">{currentPage + 1} / {pageCount}</span>
                    <button type="button" disabled={currentPage + 1 >= pageCount || !!opening} onClick={() => setPage(currentPage + 1)} className="rounded border border-white/15 px-3 py-1.5 disabled:opacity-30">{ui('다음')}</button>
                </nav>
            </footer>
        </div>
    </dialog>
}
