'use client'

import { useEffect, useState, useCallback } from 'react'
import { useAuthToken, authedFetch, formatDate } from '../app/admin/referrals/_hooks'

type SupportRow = {
    id: string
    subject: string | null
    body: string
    detected_language: string | null
    status: string
    ai_draft_reply: string | null
    ai_draft_model: string | null
    admin_reply: string | null
    replied_at: string | null
    created_at: string
    profiles?: { email: string; full_name?: string | null }
}

const STATUS_TABS = ['OPEN', 'AI_DRAFTED', 'ANSWERED', 'CLOSED', 'ALL']

const STATUS_LABELS_KO: Record<string, string> = {
    OPEN: '대기중',
    AI_DRAFTED: 'AI 초안 있음',
    ANSWERED: '답변 완료',
    CLOSED: '종료됨',
    ALL: '전체',
}

const STATUS_COLORS: Record<string, string> = {
    OPEN: 'bg-orange-500/15 text-orange-300 border-orange-500/30',
    AI_DRAFTED: 'bg-purple-500/15 text-purple-300 border-purple-500/30',
    ANSWERED: 'bg-emerald-500/15 text-emerald-300 border-emerald-500/30',
    CLOSED: 'bg-zinc-500/15 text-zinc-300 border-zinc-500/30',
}

// 유저 -> 웹어드민 문의 Inbox. AI 초안(ai_draft_reply)은 여기서만 보이고,
// "답장 발송" 버튼을 눌러야 실제로 사용자에게 나간다 - AI가 직접 발송하는
// 경로는 존재하지 않는다.
export default function SupportInboxPanel() {
    const { token, ready } = useAuthToken()
    const [statusFilter, setStatusFilter] = useState('OPEN')
    const [rows, setRows] = useState<SupportRow[]>([])
    const [loading, setLoading] = useState(false)
    const [selectedId, setSelectedId] = useState<string | null>(null)
    const [replyText, setReplyText] = useState('')
    const [sending, setSending] = useState(false)

    const fetchList = useCallback(async () => {
        if (!token) return
        setLoading(true)
        try {
            const qs = statusFilter === 'ALL' ? '' : `?status=${encodeURIComponent(statusFilter)}`
            const res = await authedFetch(token, `/api/admin/support${qs}`)
            const data = await res.json()
            setRows(data.rows || [])
        } finally {
            setLoading(false)
        }
    }, [token, statusFilter])

    useEffect(() => {
        if (ready) fetchList()
    }, [ready, fetchList])

    const selected = rows.find(r => r.id === selectedId) || null

    const openDetail = (row: SupportRow) => {
        setSelectedId(row.id)
        // AI 초안이 있으면 편집 가능한 답장 textarea를 그걸로 미리 채운다 -
        // 어드민이 그대로 보내도 되고, 고쳐서 보내도 된다.
        setReplyText(row.admin_reply || row.ai_draft_reply || '')
    }

    const sendReply = async () => {
        if (!selectedId || !replyText.trim()) return
        setSending(true)
        try {
            const res = await authedFetch(token, `/api/admin/support/${selectedId}/reply`, {
                method: 'POST',
                body: JSON.stringify({ reply: replyText.trim() }),
            })
            if (res.ok) {
                setSelectedId(null)
                setReplyText('')
                fetchList()
            } else {
                const data = await res.json().catch(() => ({}))
                alert(data.error || '답장 발송 실패')
            }
        } finally {
            setSending(false)
        }
    }

    return (
        <div>
            <h2 className="text-lg font-black mb-3">문의 Inbox</h2>

            <div className="flex flex-wrap gap-1 mb-4">
                {STATUS_TABS.map(s => (
                    <button
                        key={s}
                        onClick={() => setStatusFilter(s)}
                        className={`px-3 py-1.5 text-xs font-bold rounded-lg border transition-colors ${
                            statusFilter === s
                                ? 'bg-indigo-600 border-indigo-500 text-white'
                                : 'bg-gray-900 border-gray-800 text-gray-400 hover:text-gray-200'
                        }`}
                    >
                        {STATUS_LABELS_KO[s] || s}
                    </button>
                ))}
            </div>

            <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
                <div className="bg-gray-900 border border-gray-800 rounded-xl overflow-hidden">
                    <table className="w-full text-sm">
                        <thead className="bg-gray-800/50 text-gray-400 text-xs uppercase">
                            <tr>
                                <th className="px-3 py-2 text-left">발신자</th>
                                <th className="px-3 py-2 text-left">제목</th>
                                <th className="px-3 py-2 text-left">상태</th>
                                <th className="px-3 py-2 text-left">접수일</th>
                            </tr>
                        </thead>
                        <tbody>
                            {loading && (
                                <tr><td colSpan={4} className="px-3 py-6 text-center text-gray-500">불러오는 중...</td></tr>
                            )}
                            {!loading && rows.length === 0 && (
                                <tr><td colSpan={4} className="px-3 py-6 text-center text-gray-500">문의 내역이 없습니다</td></tr>
                            )}
                            {rows.map(row => (
                                <tr
                                    key={row.id}
                                    onClick={() => openDetail(row)}
                                    className={`cursor-pointer border-t border-gray-800 hover:bg-gray-800/40 ${selectedId === row.id ? 'bg-gray-800/60' : ''}`}
                                >
                                    <td className="px-3 py-2">{row.profiles?.email || '-'}</td>
                                    <td className="px-3 py-2 max-w-[160px] truncate">{row.subject || '(제목 없음)'}</td>
                                    <td className="px-3 py-2">
                                        <span className={`px-2 py-0.5 text-[10px] font-bold rounded-full border ${STATUS_COLORS[row.status] || ''}`}>
                                            {STATUS_LABELS_KO[row.status] || row.status}
                                        </span>
                                    </td>
                                    <td className="px-3 py-2 text-gray-400">{formatDate(row.created_at)}</td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                </div>

                <div className="bg-gray-900 border border-gray-800 rounded-xl p-4 min-h-[300px]">
                    {!selected && <div className="text-gray-500 text-sm">왼쪽 목록에서 문의를 선택하세요.</div>}
                    {selected && (
                        <div className="space-y-3 text-sm">
                            <div className="flex items-center justify-between">
                                <div>
                                    <div className="text-gray-200 font-bold">{selected.profiles?.email}</div>
                                    <div className="text-gray-500 text-xs">{formatDate(selected.created_at)}
                                        {selected.detected_language ? ` · 언어: ${selected.detected_language}` : ''}
                                    </div>
                                </div>
                                <span className={`px-2 py-0.5 text-[10px] font-bold rounded-full border ${STATUS_COLORS[selected.status] || ''}`}>
                                    {STATUS_LABELS_KO[selected.status] || selected.status}
                                </span>
                            </div>

                            <div>
                                <div className="text-gray-500 text-xs mb-1">문의 내용{selected.subject ? ` - ${selected.subject}` : ''}</div>
                                <div className="bg-gray-950 border border-gray-800 rounded-lg p-3 text-gray-200 whitespace-pre-wrap">
                                    {selected.body}
                                </div>
                            </div>

                            {selected.ai_draft_reply && (
                                <div>
                                    <div className="text-purple-300 text-xs mb-1 font-bold">AI 초안 ({selected.ai_draft_model || 'gemini'}) - 검토 후 발송하세요</div>
                                    <div className="bg-purple-950/20 border border-purple-500/30 rounded-lg p-3 text-purple-100 whitespace-pre-wrap text-xs">
                                        {selected.ai_draft_reply}
                                    </div>
                                </div>
                            )}

                            {selected.status === 'ANSWERED' ? (
                                <div>
                                    <div className="text-emerald-400 text-xs mb-1 font-bold">발송된 답장 ({formatDate(selected.replied_at)})</div>
                                    <div className="bg-gray-950 border border-gray-800 rounded-lg p-3 text-gray-300 whitespace-pre-wrap text-xs">
                                        {selected.admin_reply}
                                    </div>
                                </div>
                            ) : (
                                <div className="pt-2 border-t border-gray-800 space-y-2">
                                    <div className="text-gray-500 text-xs">답장 작성 (AI 초안이 자동으로 채워집니다 - 수정 후 발송)</div>
                                    <textarea
                                        value={replyText}
                                        onChange={e => setReplyText(e.target.value)}
                                        placeholder="답장 내용을 입력하세요"
                                        className="w-full px-3 py-2 bg-gray-950 border border-gray-800 rounded-lg text-xs"
                                        rows={6}
                                    />
                                    <button
                                        onClick={sendReply}
                                        disabled={sending || !replyText.trim()}
                                        className="w-full py-2 bg-emerald-600 hover:bg-emerald-500 disabled:opacity-50 rounded-lg text-xs font-bold"
                                    >
                                        {sending ? '발송 중...' : '답장 발송'}
                                    </button>
                                </div>
                            )}
                        </div>
                    )}
                </div>
            </div>
        </div>
    )
}
