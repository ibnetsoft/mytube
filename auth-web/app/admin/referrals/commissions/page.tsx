'use client'

import { useEffect, useState } from 'react'
import { useAuthToken, authedFetch, formatUsd, formatDate, downloadCsv } from '../_hooks'
import { LoadingBlock, EmptyBlock, ErrorBlock, Pagination, StatusBadge } from '../_components'

export default function CommissionsPage() {
    const { token, ready } = useAuthToken()
    const [rows, setRows] = useState<any[]>([])
    const [total, setTotal] = useState(0)
    const [page, setPage] = useState(1)
    const [loading, setLoading] = useState(true)
    const [error, setError] = useState('')

    const [level, setLevel] = useState('')
    const [from, setFrom] = useState('')
    const [to, setTo] = useState('')
    const [member, setMember] = useState('')
    const [sortDir, setSortDir] = useState('desc')

    const limit = 25

    useEffect(() => {
        if (!ready) return
        setLoading(true)
        const params = new URLSearchParams({ page: String(page), limit: String(limit), level, from, to, member, sortDir })
        authedFetch(token, `/api/admin/referrals/commissions?${params.toString()}`)
            .then(res => res.json())
            .then(json => {
                if (json.success) { setRows(json.data.rows); setTotal(json.data.total) }
                else setError(json.error || 'Failed to load commissions')
            })
            .catch(e => setError(e.message))
            .finally(() => setLoading(false))
    }, [ready, token, page, level, from, to, member, sortDir])

    const exportCsv = () => {
        downloadCsv('referral_commissions.csv', rows.map(r => ({
            id: r.id,
            occurred_at: r.created_at,
            level: r.commission_level,
            beneficiary: r.beneficiary?.email || r.beneficiary_id,
            source_job_id: r.source_job_id || '',
            net_settlement_amount: r.base_tokens,
            applied_rate_percent: r.rate_percent,
            commission: r.commission_tokens,
            status: r.status,
        })))
    }

    return (
        <div className="space-y-4">
            <div className="grid grid-cols-1 sm:grid-cols-3 lg:grid-cols-6 gap-2">
                <select className="bg-gray-900 border border-gray-700 rounded px-3 py-2 text-sm"
                    value={level} onChange={e => { setPage(1); setLevel(e.target.value) }}>
                    <option value="">All Levels</option>
                    <option value="1">Level 1</option>
                    <option value="2">Level 2</option>
                </select>
                <input type="date" className="bg-gray-900 border border-gray-700 rounded px-3 py-2 text-sm"
                    value={from} onChange={e => { setPage(1); setFrom(e.target.value) }} />
                <input type="date" className="bg-gray-900 border border-gray-700 rounded px-3 py-2 text-sm"
                    value={to} onChange={e => { setPage(1); setTo(e.target.value) }} />
                <input className="bg-gray-900 border border-gray-700 rounded px-3 py-2 text-sm sm:col-span-2"
                    placeholder="Search member" value={member} onChange={e => { setPage(1); setMember(e.target.value) }} />
                <button className="px-3 py-2 rounded bg-gray-800 text-sm" onClick={() => setSortDir(d => d === 'asc' ? 'desc' : 'asc')}>
                    {sortDir === 'asc' ? '↑ Oldest first' : '↓ Newest first'}
                </button>
            </div>

            <div className="flex justify-end">
                <button onClick={exportCsv} disabled={rows.length === 0}
                    className="px-3 py-1.5 rounded bg-indigo-600 hover:bg-indigo-500 disabled:opacity-40 text-sm">
                    Export CSV (current page)
                </button>
            </div>

            {(!ready || loading) && <LoadingBlock />}
            {error && <ErrorBlock message={error} />}

            {ready && !loading && !error && (
                rows.length === 0 ? <EmptyBlock /> : (
                    <div className="overflow-x-auto border border-gray-800 rounded-xl">
                        <table className="w-full text-sm">
                            <thead className="bg-gray-900 text-gray-400 text-xs uppercase">
                                <tr>
                                    <th className="px-3 py-2 text-left">발생일</th>
                                    <th className="px-3 py-2 text-left">Level</th>
                                    <th className="px-3 py-2 text-left">Beneficiary</th>
                                    <th className="px-3 py-2 text-left">원인 Job</th>
                                    <th className="px-3 py-2 text-right">Net Settlement Amount*</th>
                                    <th className="px-3 py-2 text-right">적용 %</th>
                                    <th className="px-3 py-2 text-right">수당</th>
                                    <th className="px-3 py-2 text-left">상태</th>
                                </tr>
                            </thead>
                            <tbody>
                                {rows.map(r => (
                                    <tr key={r.id} className="border-t border-gray-800 hover:bg-gray-900/60">
                                        <td className="px-3 py-2">{formatDate(r.created_at)}</td>
                                        <td className="px-3 py-2">L{r.commission_level || '?'}</td>
                                        <td className="px-3 py-2">{r.beneficiary?.full_name || r.beneficiary?.email || r.beneficiary_id}</td>
                                        <td className="px-3 py-2 font-mono text-xs">{r.source_job_id || '-'}</td>
                                        <td className="px-3 py-2 text-right">${formatUsd(r.base_tokens)}</td>
                                        <td className="px-3 py-2 text-right">{r.rate_percent}%</td>
                                        <td className="px-3 py-2 text-right font-semibold">${formatUsd(r.commission_tokens)}</td>
                                        <td className="px-3 py-2"><StatusBadge status={r.status} /></td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    </div>
                )
            )}

            <p className="text-xs text-gray-600">
                * &quot;Net Settlement Amount&quot; currently reflects <code>base_tokens</code> (the recharge amount today) — the real Net Settlement Amount calculation (refunds/discounts/fees/promotions netted out) is deferred to a future Settlement Engine Specification per <code>AIR-0221D_REFERRAL_ACTIVATION_PLAN.md</code>. Not yet implemented.
            </p>

            {ready && !loading && !error && <Pagination page={page} limit={limit} total={total} onPage={setPage} />}
        </div>
    )
}
