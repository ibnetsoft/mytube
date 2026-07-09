'use client'

import { useEffect, useState } from 'react'
import { useAuthToken, authedFetch, formatDate } from '../_hooks'
import { LoadingBlock, EmptyBlock, ErrorBlock, Pagination } from '../_components'

const ACTIONS = ['generated', 'requested', 'approved', 'rejected', 'sending', 'completed', 'reversed']
const ACTION_LABELS: Record<string, string> = {
    generated: '추천수당 생성', requested: '출금요청', approved: '승인', rejected: '거절', sending: 'Sending', completed: 'Completed', reversed: 'Reversed',
}

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
                else setError(json.error || 'Failed to load audit log')
            })
            .catch(e => setError(e.message))
            .finally(() => setLoading(false))
    }, [ready, token, page, entityType, action, member, admin, from, to])

    return (
        <div className="space-y-4">
            <div className="grid grid-cols-1 sm:grid-cols-3 lg:grid-cols-6 gap-2">
                <select className="bg-gray-900 border border-gray-700 rounded px-3 py-2 text-sm"
                    value={entityType} onChange={e => { setPage(1); setEntityType(e.target.value) }}>
                    <option value="">All Types</option>
                    <option value="commission">Commission</option>
                    <option value="withdrawal">Withdrawal</option>
                </select>
                <select className="bg-gray-900 border border-gray-700 rounded px-3 py-2 text-sm"
                    value={action} onChange={e => { setPage(1); setAction(e.target.value) }}>
                    <option value="">All Actions</option>
                    {ACTIONS.map(a => <option key={a} value={a}>{ACTION_LABELS[a]}</option>)}
                </select>
                <input className="bg-gray-900 border border-gray-700 rounded px-3 py-2 text-sm"
                    placeholder="Member" value={member} onChange={e => { setPage(1); setMember(e.target.value) }} />
                <input className="bg-gray-900 border border-gray-700 rounded px-3 py-2 text-sm"
                    placeholder="Admin" value={admin} onChange={e => { setPage(1); setAdmin(e.target.value) }} />
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
                                    <th className="px-3 py-2 text-left">Time</th>
                                    <th className="px-3 py-2 text-left">Type</th>
                                    <th className="px-3 py-2 text-left">Action</th>
                                    <th className="px-3 py-2 text-left">Entity</th>
                                    <th className="px-3 py-2 text-left">Admin</th>
                                    <th className="px-3 py-2 text-left">Reason</th>
                                </tr>
                            </thead>
                            <tbody>
                                {rows.map(r => (
                                    <tr key={r.id} className="border-t border-gray-800 hover:bg-gray-900/60">
                                        <td className="px-3 py-2">{formatDate(r.created_at)}</td>
                                        <td className="px-3 py-2 capitalize">{r.entity_type}</td>
                                        <td className="px-3 py-2">{ACTION_LABELS[r.action] || r.action}</td>
                                        <td className="px-3 py-2 font-mono text-xs">{r.entity_id}</td>
                                        <td className="px-3 py-2">{r.actor?.full_name || r.actor?.email || (r.actor_id ? r.actor_id : 'System')}</td>
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
