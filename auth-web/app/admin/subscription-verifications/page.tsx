'use client'

import { useEffect, useState, useCallback } from 'react'
import { useAuthToken, authedFetch, formatDate } from '../referrals/_hooks'

type VerificationRow = {
    id: string
    provider: string
    status: string
    rule_score: number | null
    ai_recommended_action: string | null
    ai_confidence: number | null
    ai_visual_tampering_risk: string | null
    ai_suspicious_reasons: string[] | null
    duplicate_image_flag: boolean
    masked_account_email: string | null
    document_type: string | null
    subscription_status_raw: string | null
    payment_date: string | null
    next_renewal_date: string | null
    rejection_reason: string | null
    expires_at: string | null
    created_at: string
    profiles?: { email: string }
}

const STATUS_TABS = ['NEEDS_REVIEW', 'UPLOADED', 'ANALYZING', 'APPROVED', 'REJECTED', 'EXPIRED', 'REVOKED', 'ALL']

const STATUS_COLORS: Record<string, string> = {
    UPLOADED: 'bg-gray-500/15 text-gray-300 border-gray-500/30',
    ANALYZING: 'bg-blue-500/15 text-blue-300 border-blue-500/30 animate-pulse',
    NEEDS_REVIEW: 'bg-orange-500/15 text-orange-300 border-orange-500/30',
    APPROVED: 'bg-emerald-500/15 text-emerald-300 border-emerald-500/30',
    REJECTED: 'bg-red-500/15 text-red-300 border-red-500/30',
    EXPIRED: 'bg-zinc-500/15 text-zinc-300 border-zinc-500/30',
    REVOKED: 'bg-zinc-500/15 text-zinc-300 border-zinc-500/30',
}

export default function SubscriptionVerificationsPage() {
    const { token, ready } = useAuthToken()
    const [statusFilter, setStatusFilter] = useState('NEEDS_REVIEW')
    const [rows, setRows] = useState<VerificationRow[]>([])
    const [loading, setLoading] = useState(false)
    const [selectedId, setSelectedId] = useState<string | null>(null)
    const [detail, setDetail] = useState<any>(null)
    const [detailLoading, setDetailLoading] = useState(false)
    const [rejectReason, setRejectReason] = useState('')
    const [actionBusy, setActionBusy] = useState(false)

    const fetchList = useCallback(async () => {
        if (!token) return
        setLoading(true)
        try {
            const qs = statusFilter === 'ALL' ? '' : `?status=${encodeURIComponent(statusFilter)}`
            const res = await authedFetch(token, `/api/admin/subscription-verifications${qs}`)
            const data = await res.json()
            setRows(data.rows || [])
        } finally {
            setLoading(false)
        }
    }, [token, statusFilter])

    useEffect(() => {
        if (ready) fetchList()
    }, [ready, fetchList])

    const openDetail = async (id: string) => {
        setSelectedId(id)
        setDetail(null)
        setRejectReason('')
        setDetailLoading(true)
        try {
            const res = await authedFetch(token, `/api/admin/subscription-verifications/${id}`)
            const data = await res.json()
            setDetail(data)
        } finally {
            setDetailLoading(false)
        }
    }

    const approve = async () => {
        if (!selectedId) return
        setActionBusy(true)
        try {
            const res = await authedFetch(token, `/api/admin/subscription-verifications/${selectedId}/approve`, { method: 'POST' })
            if (res.ok) {
                setSelectedId(null)
                fetchList()
            } else {
                alert('승인 실패')
            }
        } finally {
            setActionBusy(false)
        }
    }

    const reject = async () => {
        if (!selectedId) return
        setActionBusy(true)
        try {
            const res = await authedFetch(token, `/api/admin/subscription-verifications/${selectedId}/reject`, {
                method: 'POST',
                body: JSON.stringify({ reason: rejectReason }),
            })
            if (res.ok) {
                setSelectedId(null)
                fetchList()
            } else {
                alert('반려 실패')
            }
        } finally {
            setActionBusy(false)
        }
    }

    return (
        <div>
            <h1 className="text-xl font-bold mb-4">구독 인증 뱃지 관리</h1>

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
                        {s}
                    </button>
                ))}
            </div>

            <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
                <div className="bg-gray-900 border border-gray-800 rounded-xl overflow-hidden">
                    <table className="w-full text-sm">
                        <thead className="bg-gray-800/50 text-gray-400 text-xs uppercase">
                            <tr>
                                <th className="px-3 py-2 text-left">Email</th>
                                <th className="px-3 py-2 text-left">Provider</th>
                                <th className="px-3 py-2 text-left">Status</th>
                                <th className="px-3 py-2 text-left">Score</th>
                                <th className="px-3 py-2 text-left">Submitted</th>
                            </tr>
                        </thead>
                        <tbody>
                            {loading && (
                                <tr><td colSpan={5} className="px-3 py-6 text-center text-gray-500">Loading...</td></tr>
                            )}
                            {!loading && rows.length === 0 && (
                                <tr><td colSpan={5} className="px-3 py-6 text-center text-gray-500">No submissions</td></tr>
                            )}
                            {rows.map(row => (
                                <tr
                                    key={row.id}
                                    onClick={() => openDetail(row.id)}
                                    className={`cursor-pointer border-t border-gray-800 hover:bg-gray-800/40 ${selectedId === row.id ? 'bg-gray-800/60' : ''}`}
                                >
                                    <td className="px-3 py-2">{row.profiles?.email || '-'}</td>
                                    <td className="px-3 py-2">{row.provider}</td>
                                    <td className="px-3 py-2">
                                        <span className={`px-2 py-0.5 text-[10px] font-bold rounded-full border ${STATUS_COLORS[row.status] || ''}`}>
                                            {row.status}
                                            {row.duplicate_image_flag ? ' · DUP' : ''}
                                        </span>
                                    </td>
                                    <td className="px-3 py-2">{row.rule_score ?? '-'}</td>
                                    <td className="px-3 py-2 text-gray-400">{formatDate(row.created_at)}</td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                </div>

                <div className="bg-gray-900 border border-gray-800 rounded-xl p-4 min-h-[300px]">
                    {!selectedId && <div className="text-gray-500 text-sm">왼쪽 목록에서 항목을 선택하세요.</div>}
                    {selectedId && detailLoading && <div className="text-gray-500 text-sm">Loading...</div>}
                    {selectedId && detail?.verification && (
                        <div className="space-y-3 text-sm">
                            <div className="flex items-center justify-between">
                                <span className="text-gray-400">{detail.verification.profiles?.email}</span>
                                <span className={`px-2 py-0.5 text-[10px] font-bold rounded-full border ${STATUS_COLORS[detail.verification.status] || ''}`}>
                                    {detail.verification.status}
                                </span>
                            </div>

                            {detail.signed_url && (
                                <a href={detail.signed_url} target="_blank" rel="noreferrer">
                                    <img src={detail.signed_url} alt="evidence" className="max-h-64 rounded-lg border border-gray-800 object-contain" />
                                </a>
                            )}

                            <div className="grid grid-cols-2 gap-2 text-xs">
                                <div><span className="text-gray-500">Document type</span><div>{detail.verification.document_type || '-'}</div></div>
                                <div><span className="text-gray-500">Status (raw)</span><div>{detail.verification.subscription_status_raw || '-'}</div></div>
                                <div><span className="text-gray-500">Masked email</span><div>{detail.verification.masked_account_email || '-'}</div></div>
                                <div><span className="text-gray-500">Payment date</span><div>{detail.verification.payment_date || '-'}</div></div>
                                <div><span className="text-gray-500">Next renewal</span><div>{detail.verification.next_renewal_date || '-'}</div></div>
                                <div><span className="text-gray-500">Amount</span><div>{detail.verification.amount ? `${detail.verification.currency || ''} ${detail.verification.amount}` : '-'}</div></div>
                                <div><span className="text-gray-500">Rule score</span><div>{detail.verification.rule_score ?? '-'}</div></div>
                                <div><span className="text-gray-500">AI confidence</span><div>{detail.verification.ai_confidence ?? '-'}</div></div>
                                <div><span className="text-gray-500">Tampering risk</span><div>{detail.verification.ai_visual_tampering_risk || '-'}</div></div>
                                <div><span className="text-gray-500">Duplicate image</span><div>{detail.verification.duplicate_image_flag ? 'YES' : 'no'}</div></div>
                            </div>

                            {Array.isArray(detail.verification.ai_suspicious_reasons) && detail.verification.ai_suspicious_reasons.length > 0 && (
                                <div className="text-xs">
                                    <span className="text-gray-500">Suspicious reasons</span>
                                    <ul className="list-disc list-inside text-orange-300">
                                        {detail.verification.ai_suspicious_reasons.map((r: string, i: number) => <li key={i}>{r}</li>)}
                                    </ul>
                                </div>
                            )}

                            {detail.verification.status !== 'APPROVED' && (
                                <div className="pt-2 border-t border-gray-800 space-y-2">
                                    <button
                                        onClick={approve}
                                        disabled={actionBusy}
                                        className="w-full py-2 bg-emerald-600 hover:bg-emerald-500 disabled:opacity-50 rounded-lg text-xs font-bold"
                                    >
                                        승인
                                    </button>
                                    <textarea
                                        value={rejectReason}
                                        onChange={e => setRejectReason(e.target.value)}
                                        placeholder="반려 사유 (선택)"
                                        className="w-full px-2 py-1.5 bg-gray-950 border border-gray-800 rounded-lg text-xs"
                                        rows={2}
                                    />
                                    <button
                                        onClick={reject}
                                        disabled={actionBusy}
                                        className="w-full py-2 bg-red-600 hover:bg-red-500 disabled:opacity-50 rounded-lg text-xs font-bold"
                                    >
                                        반려
                                    </button>
                                </div>
                            )}

                            <div className="pt-2 border-t border-gray-800">
                                <span className="text-gray-500 text-xs">Audit log</span>
                                <ul className="text-[11px] text-gray-400 space-y-0.5 mt-1">
                                    {(detail.audit_log || []).map((a: any) => (
                                        <li key={a.id}>{formatDate(a.created_at)} — {a.action}{a.reason ? ` (${a.reason})` : ''}</li>
                                    ))}
                                </ul>
                            </div>
                        </div>
                    )}
                </div>
            </div>
        </div>
    )
}
