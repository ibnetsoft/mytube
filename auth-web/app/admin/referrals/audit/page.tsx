'use client'

import { useEffect, useState } from 'react'
import { useAuthToken, authedFetch, formatDate } from '../_hooks'
import { LoadingBlock, EmptyBlock, ErrorBlock, Pagination } from '../_components'

const ACTIONS = ['generated', 'requested', 'approved', 'rejected', 'sending', 'completed', 'reversed']
const ACTION_LABELS: Record<string, string> = {
    generated: '추천수당 생성', requested: '출금요청', approved: '승인', rejected: '거절', sending: '전송 중', completed: '완료', reversed: '취소됨',
}
const ENTITY_TYPE_LABELS: Record<string, string> = { commission: '커미션', withdrawal: '출금' }

export default function AuditPage() {
    const { token, ready } = useAuthToken()
    const [rows, setRows] = useState<any[]>([])
    const [total, setTotal] = useState(0)
    const [page, setPage] = useState(1)
    const [loading, setLoading] = useState(true)
    const [error, setError] = useState('')

    const [entityType, setEntityType] = useState('')
    const [action, setAction] = useState('')
    const [member, setMember] = useState('')
    const [admin, setAdmin] = useState('')
    const [from, setFrom] = useState('')
    const [to, setTo] = useState('')

    const limit = 30

    useEffect(() => {
        if (!ready) return
        setLoading(true)
        const params = new URLSearchParams({ page: String(page), limit: String(limit), entityType, action, member, admin, from, to })
        authedFetch(token, `/api/admin/referrals/audit?${params.toString()}`)
            .then(res => res.json())
            .then(json => {
                if (json.success) { setRows(json.data.rows); setTotal(json.data.total) }
                else setError(json.error || '감사 로그를 불러오지 못했습니다')
            })
            .catch(e => setError(e.message))
            .finally(() => setLoading(false))
    }, [ready, token, page, entityType, action, member, admin, from, to])

    return (
        <div className="space-y-4">
            <div className="grid grid-cols-1 sm:grid-cols-3 lg:grid-cols-6 gap-2">
                <select className="bg-gray-900 border border-gray-700 rounded px-3 py-2 text-sm"
                    value={entityType} onChange={e => { setPage(1); setEntityType(e.target.value) }}>
                    <option value="">전체 유형</option>
                    <option value="commission">커미션</option>
                    <option value="withdrawal">출금</option>
                </select>
                <select className="bg-gray-900 border border-gray-700 rounded px-3 py-2 text-sm"
                    value={action} onChange={e => { setPage(1); setAction(e.target.value) }}>
                    <option value="">전체 액션</option>
                    {ACTIONS.map(a => <option key={a} value={a}>{ACTION_LABELS[a]}</option>)}
                </select>
                <input className="bg-gray-900 border border-gray-700 rounded px-3 py-2 text-sm"
                    placeholder="멤버" value={member} onChange={e => { setPage(1); setMember(e.target.value) }} />
                <input className="bg-gray-900 border border-gray-700 rounded px-3 py-2 text-sm"
                    placeholder="관리자" value={admin} onChange={e => { setPage(1); setAdmin(e.target.value) }} />
                <input type="date" className="bg-gray-900 border border-gray-700 rounded px-3 py-2 text-sm"
                    value={from} onChange={e => { setPage(1); setFrom(e.target.value) }} />
                <input type="date" className="bg-gray-900 border border-gray-700 rounded px-3 py-2 text-sm"
                    value={to} onChange={e => { setPage(1); setTo(e.target.value) }} />
            </div>

            {(!ready || loading) && <LoadingBlock />}
            {error && <ErrorBlock message={error} />}

            {ready && !loading && !error && (
                rows.length === 0 ? <EmptyBlock /> : (
                    <div className="overflow-x-auto border border-gray-800 rounded-xl">
                        <table className="w-full text-sm">
                            <thead className="bg-gray-900 text-gray-400 text-xs uppercase">
                                <tr>
                                    <th className="px-3 py-2 text-left">시각</th>
                                    <th className="px-3 py-2 text-left">유형</th>
                                    <th className="px-3 py-2 text-left">액션</th>
                                    <th className="px-3 py-2 text-left">엔티티</th>
                                    <th className="px-3 py-2 text-left">관리자</th>
                                    <th className="px-3 py-2 text-left">사유</th>
                                </tr>
                            </thead>
                            <tbody>
                                {rows.map(r => (
                                    <tr key={r.id} className="border-t border-gray-800 hover:bg-gray-900/60">
                                        <td className="px-3 py-2">{formatDate(r.created_at)}</td>
                                        <td className="px-3 py-2">{ENTITY_TYPE_LABELS[r.entity_type] || r.entity_type}</td>
                                        <td className="px-3 py-2">{ACTION_LABELS[r.action] || r.action}</td>
                                        <td className="px-3 py-2 font-mono text-xs">{r.entity_id}</td>
                                        <td className="px-3 py-2">{r.actor?.full_name || r.actor?.email || (r.actor_id ? r.actor_id : '시스템')}</td>
                                        <td className="px-3 py-2 text-gray-400">{r.reason || '-'}</td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    </div>
                )
            )}

            {ready && !loading && !error && <Pagination page={page} limit={limit} total={total} onPage={setPage} />}
        </div>
    )
}
