'use client'

import { useEffect, useState } from 'react'
import { useAuthToken, authedFetch, formatUsd, formatDate } from '../_hooks'
import { LoadingBlock, EmptyBlock, ErrorBlock, Pagination, StatusBadge, STATUS_LABELS_KO } from '../_components'

const STATUSES = ['REQUESTED', 'APPROVED', 'SENDING', 'COMPLETED', 'REJECTED']

export default function WithdrawalsPage() {
    const { token, ready } = useAuthToken()
    const [rows, setRows] = useState<any[]>([])
    const [total, setTotal] = useState(0)
    const [page, setPage] = useState(1)
    const [loading, setLoading] = useState(true)
    const [error, setError] = useState('')
    const [actionError, setActionError] = useState('')
    const [processingId, setProcessingId] = useState('')
    const [detailRow, setDetailRow] = useState<any>(null)

    const [status, setStatus] = useState('')
    const [from, setFrom] = useState('')
    const [to, setTo] = useState('')
    const [member, setMember] = useState('')

    const limit = 25

    const load = () => {
        if (!ready) return
        setLoading(true)
        const params = new URLSearchParams({ page: String(page), limit: String(limit), status, from, to, member })
        authedFetch(token, `/api/admin/referrals/withdrawals?${params.toString()}`)
            .then(res => res.json())
            .then(json => {
                if (json.success) { setRows(json.data.rows); setTotal(json.data.total) }
                else setError(json.error || '출금 내역을 불러오지 못했습니다')
            })
            .catch(e => setError(e.message))
            .finally(() => setLoading(false))
    }

    useEffect(load, [ready, token, page, status, from, to, member])

    const act = async (id: string, action: 'approve' | 'reject') => {
        if (!confirm(`이 출금을 ${action === 'approve' ? '승인하고 완료 처리' : '반려'}하시겠습니까?`)) return
        setActionError('')
        setProcessingId(id)
        try {
            const res = await authedFetch(token, `/api/admin/referrals/withdrawals/${id}`, {
                method: 'PATCH',
                body: JSON.stringify({ action }),
            })
            const json = await res.json()
            if (!json.success) setActionError(json.error || '처리에 실패했습니다')
            else {
                setDetailRow(null)
                load()
            }
        } catch (e: any) {
            setActionError(e.message)
        } finally {
            setProcessingId('')
        }
    }

    return (
        <div className="space-y-4">
            <div className="grid grid-cols-1 sm:grid-cols-3 lg:grid-cols-5 gap-2">
                <select className="bg-gray-900 border border-gray-700 rounded px-3 py-2 text-sm"
                    value={status} onChange={e => { setPage(1); setStatus(e.target.value) }}>
                    <option value="">전체 상태</option>
                    {STATUSES.map(s => <option key={s} value={s}>{STATUS_LABELS_KO[s] || s}</option>)}
                </select>
                <input type="date" className="bg-gray-900 border border-gray-700 rounded px-3 py-2 text-sm"
                    value={from} onChange={e => { setPage(1); setFrom(e.target.value) }} />
                <input type="date" className="bg-gray-900 border border-gray-700 rounded px-3 py-2 text-sm"
                    value={to} onChange={e => { setPage(1); setTo(e.target.value) }} />
                <input className="bg-gray-900 border border-gray-700 rounded px-3 py-2 text-sm sm:col-span-2"
                    placeholder="멤버 검색" value={member} onChange={e => { setPage(1); setMember(e.target.value) }} />
            </div>

            {actionError && <ErrorBlock message={actionError} />}
            {(!ready || loading) && <LoadingBlock />}
            {error && <ErrorBlock message={error} />}

            {ready && !loading && !error && (
                rows.length === 0 ? <EmptyBlock /> : (
                    <div className="overflow-x-auto border border-gray-800 rounded-xl">
                        <table className="w-full text-sm">
                            <thead className="bg-gray-900 text-gray-400 text-xs uppercase">
                                <tr>
                                    <th className="px-3 py-2 text-left">요청일</th>
                                    <th className="px-3 py-2 text-left">멤버</th>
                                    <th className="px-3 py-2 text-right">금액</th>
                                    <th className="px-3 py-2 text-left">상태</th>
                                    <th className="px-3 py-2 text-right">작업</th>
                                </tr>
                            </thead>
                            <tbody>
                                {rows.map(r => (
                                    <tr key={r.id} className="border-t border-gray-800 hover:bg-gray-900/60">
                                        <td className="px-3 py-2">{formatDate(r.requested_at)}</td>
                                        <td className="px-3 py-2">{r.member?.full_name || r.member?.email || r.user_id}</td>
                                        <td className="px-3 py-2 text-right">${formatUsd(r.amount)}</td>
                                        <td className="px-3 py-2"><StatusBadge status={r.status} /></td>
                                        <td className="px-3 py-2 text-right space-x-2">
                                            <button className="text-indigo-400 hover:underline text-xs" onClick={() => setDetailRow(r)}>상세</button>
                                            {!['COMPLETED', 'REJECTED'].includes(r.status) && (
                                                <>
                                                    <button
                                                        className="text-green-400 hover:underline text-xs disabled:opacity-40"
                                                        disabled={processingId === r.id}
                                                        onClick={() => act(r.id, 'approve')}
                                                    >승인</button>
                                                    <button
                                                        className="text-red-400 hover:underline text-xs disabled:opacity-40"
                                                        disabled={processingId === r.id}
                                                        onClick={() => act(r.id, 'reject')}
                                                    >반려</button>
                                                </>
                                            )}
                                        </td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    </div>
                )
            )}

            {ready && !loading && !error && <Pagination page={page} limit={limit} total={total} onPage={setPage} />}

            {detailRow && (
                <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50 p-4" onClick={() => setDetailRow(null)}>
                    <div className="bg-gray-900 border border-gray-700 rounded-xl p-6 max-w-lg w-full" onClick={e => e.stopPropagation()}>
                        <div className="flex justify-between items-center mb-4">
                            <h3 className="text-lg font-bold">출금 상세</h3>
                            <button onClick={() => setDetailRow(null)} className="text-gray-400 hover:text-white">✕</button>
                        </div>
                        <dl className="text-sm space-y-2">
                            <div className="flex justify-between"><dt className="text-gray-400">ID</dt><dd className="font-mono text-xs">{detailRow.id}</dd></div>
                            <div className="flex justify-between"><dt className="text-gray-400">멤버</dt><dd>{detailRow.member?.email || detailRow.user_id}</dd></div>
                            <div className="flex justify-between"><dt className="text-gray-400">금액</dt><dd>${formatUsd(detailRow.amount)}</dd></div>
                            <div className="flex justify-between"><dt className="text-gray-400">상태</dt><dd><StatusBadge status={detailRow.status} /></dd></div>
                            <div className="flex justify-between"><dt className="text-gray-400">지갑 주소</dt><dd className="font-mono text-xs break-all">{detailRow.wallet_address}</dd></div>
                            <div className="flex justify-between"><dt className="text-gray-400">요청일</dt><dd>{formatDate(detailRow.requested_at)}</dd></div>
                            <div className="flex justify-between"><dt className="text-gray-400">승인일</dt><dd>{formatDate(detailRow.approved_at)}</dd></div>
                            <div className="flex justify-between"><dt className="text-gray-400">전송일</dt><dd>{formatDate(detailRow.sent_at)}</dd></div>
                            <div className="flex justify-between"><dt className="text-gray-400">완료일</dt><dd>{formatDate(detailRow.completed_at)}</dd></div>
                            <div className="flex justify-between"><dt className="text-gray-400">반려일</dt><dd>{formatDate(detailRow.rejected_at)}</dd></div>
                            <div className="flex justify-between"><dt className="text-gray-400">사유</dt><dd>{detailRow.reason || '-'}</dd></div>
                        </dl>
                    </div>
                </div>
            )}
        </div>
    )
}
