'use client'

import { Fragment, useEffect, useState, useCallback } from 'react'
import { useAuthToken, authedFetch, formatDate } from '../app/admin/referrals/_hooks'

type AnnouncementRow = {
    id: string
    title: string
    body: string
    is_pinned: boolean
    is_published: boolean
    pinned_at: string | null
    published_at: string | null
    created_at: string
    author?: { email: string }
    // AIR-0229: 한글 원문(title/body) 저장 시 서버가 자동번역해 채운다.
    translation_status?: 'pending' | 'running' | 'completed' | 'failed'
    title_en?: string | null
    body_en?: string | null
    title_vi?: string | null
    body_vi?: string | null
    title_th?: string | null
    body_th?: string | null
}

const PREVIEW_LANGS = [
    { key: 'ko', label: '🇰🇷 KO' },
    { key: 'en', label: '🇺🇸 EN' },
    { key: 'vi', label: '🇻🇳 VI' },
    { key: 'th', label: '🇹🇭 TH' },
] as const
type PreviewLang = typeof PREVIEW_LANGS[number]['key']

const TRANSLATION_STATUS_LABEL: Record<string, string> = {
    completed: '번역 완료',
    running: '번역 중',
    failed: '번역 실패',
    pending: '번역 대기',
}

// 웹어드민 -> 전체 유저 공지사항 게시판 관리. 쪽지(1:1)가 아니라 게시판
// (1:N) - 여기서 작성한 글은 모든 로그인 유저가 동일하게 본다.
export default function AnnouncementsAdminPanel() {
    const { token, ready } = useAuthToken()
    const [rows, setRows] = useState<AnnouncementRow[]>([])
    const [loading, setLoading] = useState(false)
    const [title, setTitle] = useState('')
    const [body, setBody] = useState('')
    const [pinnedOnCreate, setPinnedOnCreate] = useState(false)
    const [posting, setPosting] = useState(false)
    const [busyId, setBusyId] = useState<string | null>(null)
    const [expandedId, setExpandedId] = useState<string | null>(null)
    const [previewLang, setPreviewLang] = useState<PreviewLang>('ko')

    const toggleExpand = (id: string) => {
        setPreviewLang('ko')
        setExpandedId(prev => (prev === id ? null : id))
    }

    const fetchList = useCallback(async () => {
        if (!token) return
        setLoading(true)
        try {
            const res = await authedFetch(token, '/api/admin/announcements')
            const data = await res.json()
            setRows(data.rows || [])
        } finally {
            setLoading(false)
        }
    }, [token])

    useEffect(() => {
        if (ready) fetchList()
    }, [ready, fetchList])

    const submitNew = async () => {
        if (!title.trim() || !body.trim()) return
        setPosting(true)
        try {
            const res = await authedFetch(token, '/api/admin/announcements', {
                method: 'POST',
                body: JSON.stringify({ title: title.trim(), body: body.trim(), is_pinned: pinnedOnCreate }),
            })
            if (res.ok) {
                setTitle('')
                setBody('')
                setPinnedOnCreate(false)
                fetchList()
            } else {
                const data = await res.json().catch(() => ({}))
                alert(data.error || '등록 실패')
            }
        } finally {
            setPosting(false)
        }
    }

    const togglePin = async (row: AnnouncementRow) => {
        setBusyId(row.id)
        try {
            const res = await authedFetch(token, `/api/admin/announcements/${row.id}`, {
                method: 'PATCH',
                body: JSON.stringify({ is_pinned: !row.is_pinned }),
            })
            if (res.ok) fetchList()
        } finally {
            setBusyId(null)
        }
    }

    const togglePublish = async (row: AnnouncementRow) => {
        setBusyId(row.id)
        try {
            const res = await authedFetch(token, `/api/admin/announcements/${row.id}`, {
                method: 'PATCH',
                body: JSON.stringify({ is_published: !row.is_published }),
            })
            if (res.ok) fetchList()
        } finally {
            setBusyId(null)
        }
    }

    const removeRow = async (row: AnnouncementRow) => {
        if (!confirm(`"${row.title}" 공지를 삭제할까요?`)) return
        setBusyId(row.id)
        try {
            const res = await authedFetch(token, `/api/admin/announcements/${row.id}`, { method: 'DELETE' })
            if (res.ok) fetchList()
        } finally {
            setBusyId(null)
        }
    }

    return (
        <div className="space-y-6">
            <h2 className="text-lg font-black">공지사항 게시판 관리</h2>

            <div className="bg-gray-900 border border-gray-800 rounded-xl p-4 space-y-3">
                <div className="flex items-center justify-between gap-4">
                    <div className="text-sm font-bold text-gray-300">새 공지 작성</div>
                    <div className="text-[10px] text-gray-500">한글로 작성하면 게시 시 영어/베트남어/태국어로 자동 번역되어 데스크톱 앱의 언어모드에 맞게 표시됩니다.</div>
                </div>
                <input
                    value={title}
                    onChange={e => setTitle(e.target.value)}
                    placeholder="제목"
                    maxLength={200}
                    className="w-full px-3 py-2 bg-gray-950 border border-gray-800 rounded-lg text-sm text-white"
                />
                <textarea
                    value={body}
                    onChange={e => setBody(e.target.value)}
                    placeholder="내용"
                    rows={4}
                    maxLength={10000}
                    className="w-full px-3 py-2 bg-gray-950 border border-gray-800 rounded-lg text-sm text-white"
                />
                <label className="flex items-center gap-2 text-xs text-gray-400">
                    <input type="checkbox" checked={pinnedOnCreate} onChange={e => setPinnedOnCreate(e.target.checked)} />
                    작성과 동시에 상단 고정
                </label>
                <button
                    onClick={submitNew}
                    disabled={posting || !title.trim() || !body.trim()}
                    className="px-4 py-2 bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 rounded-lg text-xs font-bold text-white"
                >
                    {posting ? '등록 중...' : '전체 유저에게 게시'}
                </button>
            </div>

            <div className="bg-gray-900 border border-gray-800 rounded-xl overflow-hidden">
                <table className="w-full text-sm">
                    <thead className="bg-gray-800/50 text-gray-400 text-xs uppercase">
                        <tr>
                            <th className="px-3 py-2 text-left">제목</th>
                            <th className="px-3 py-2 text-left">작성자</th>
                            <th className="px-3 py-2 text-left">상태</th>
                            <th className="px-3 py-2 text-left">작성일</th>
                            <th className="px-3 py-2 text-left">관리</th>
                        </tr>
                    </thead>
                    <tbody>
                        {loading && (
                            <tr><td colSpan={5} className="px-3 py-6 text-center text-gray-500">불러오는 중...</td></tr>
                        )}
                        {!loading && rows.length === 0 && (
                            <tr><td colSpan={5} className="px-3 py-6 text-center text-gray-500">등록된 공지가 없습니다</td></tr>
                        )}
                        {rows.map(row => (
                            <Fragment key={row.id}>
                                <tr className="border-t border-gray-800">
                                    <td className="px-3 py-2 max-w-[240px]">
                                        <div className="font-bold text-white truncate">{row.is_pinned ? '📌 ' : ''}{row.title}</div>
                                        <div className="text-gray-500 text-xs truncate">{row.body}</div>
                                    </td>
                                    <td className="px-3 py-2 text-gray-400">{row.author?.email || '-'}</td>
                                    <td className="px-3 py-2">
                                        <div className="flex flex-col gap-1 items-start">
                                            <span className={`px-2 py-0.5 text-[10px] font-bold rounded-full border ${row.is_published ? 'bg-emerald-500/15 text-emerald-300 border-emerald-500/30' : 'bg-zinc-500/15 text-zinc-300 border-zinc-500/30'}`}>
                                                {row.is_published ? '게시중' : '초안'}
                                            </span>
                                            <span className={`px-2 py-0.5 text-[10px] font-bold rounded-full border ${
                                                row.translation_status === 'completed' ? 'bg-blue-500/15 text-blue-300 border-blue-500/30' :
                                                row.translation_status === 'failed' ? 'bg-red-500/15 text-red-300 border-red-500/30' :
                                                'bg-zinc-500/15 text-zinc-400 border-zinc-500/30'
                                            }`}>
                                                {TRANSLATION_STATUS_LABEL[row.translation_status || 'pending']}
                                            </span>
                                        </div>
                                    </td>
                                    <td className="px-3 py-2 text-gray-400">{formatDate(row.created_at)}</td>
                                    <td className="px-3 py-2">
                                        <div className="flex gap-1.5 flex-wrap">
                                            <button
                                                onClick={() => toggleExpand(row.id)}
                                                className="px-2 py-1 rounded text-[10px] font-bold bg-indigo-900/50 text-indigo-300"
                                            >
                                                {expandedId === row.id ? '번역 닫기' : '번역 보기'}
                                            </button>
                                            <button
                                                onClick={() => togglePin(row)}
                                                disabled={busyId === row.id}
                                                className={`px-2 py-1 rounded text-[10px] font-bold ${row.is_pinned ? 'bg-amber-600 text-white' : 'bg-gray-800 text-gray-300'} disabled:opacity-50`}
                                            >
                                                {row.is_pinned ? '고정 해제' : '상단 고정'}
                                            </button>
                                            <button
                                                onClick={() => togglePublish(row)}
                                                disabled={busyId === row.id}
                                                className="px-2 py-1 rounded text-[10px] font-bold bg-gray-800 text-gray-300 disabled:opacity-50"
                                            >
                                                {row.is_published ? '비공개' : '게시'}
                                            </button>
                                            <button
                                                onClick={() => removeRow(row)}
                                                disabled={busyId === row.id}
                                                className="px-2 py-1 rounded text-[10px] font-bold bg-red-900/50 text-red-300 disabled:opacity-50"
                                            >
                                                삭제
                                            </button>
                                        </div>
                                    </td>
                                </tr>
                                {expandedId === row.id && (
                                    <tr className="border-t border-gray-800 bg-gray-950/60">
                                        <td colSpan={5} className="px-3 py-3">
                                            <div className="flex gap-1.5 mb-2">
                                                {PREVIEW_LANGS.map(l => (
                                                    <button
                                                        key={l.key}
                                                        onClick={() => setPreviewLang(l.key)}
                                                        className={`px-2.5 py-1 rounded text-[10px] font-bold ${previewLang === l.key ? 'bg-indigo-600 text-white' : 'bg-gray-800 text-gray-400'}`}
                                                    >
                                                        {l.label}
                                                    </button>
                                                ))}
                                            </div>
                                            <div className="text-xs text-gray-300 whitespace-pre-wrap">
                                                <p className="font-bold text-white">
                                                    {previewLang === 'ko' ? row.title : (row[`title_${previewLang}`] || '(번역 대기중 — 한글로 표시됩니다)')}
                                                </p>
                                                <p className="mt-1 text-gray-400">
                                                    {previewLang === 'ko' ? row.body : (row[`body_${previewLang}`] || row.body)}
                                                </p>
                                            </div>
                                        </td>
                                    </tr>
                                )}
                            </Fragment>
                        ))}
                    </tbody>
                </table>
            </div>
        </div>
    )
}
