'use client'

import { useEffect, useMemo, useState } from 'react'
import Link from 'next/link'
import { useAuthToken, authedFetch, formatUsd, formatDate } from '../_hooks'
import { LoadingBlock, EmptyBlock, ErrorBlock, Pagination, OrgMemberCard } from '../_components'

interface OrgRow {
    id: string
    email: string
    full_name: string | null
    referral_code: string | null
    referred_by: string | null
    sponsor_name: string | null
    country: string | null
    created_at: string
    level: number
    direct_referrals: number
    commission_total: number
    commission_level1_total: number
    commission_level2_total: number
    is_active: boolean
}

export default function OrganizationPage() {
    const { token, ready } = useAuthToken()
    const [view, setView] = useState<'table' | 'tree'>('table')
    const [rows, setRows] = useState<OrgRow[]>([])
    const [total, setTotal] = useState(0)
    const [page, setPage] = useState(1)
    const [loading, setLoading] = useState(true)
    const [error, setError] = useState('')

    const [search, setSearch] = useState('')
    const [country, setCountry] = useState('')
    const [from, setFrom] = useState('')
    const [to, setTo] = useState('')
    const [activity, setActivity] = useState('all')
    const [sortBy, setSortBy] = useState('created_at')
    const [sortDir, setSortDir] = useState('desc')

    const limit = 20

    useEffect(() => {
        if (!ready) return
        setLoading(true)
        const params = new URLSearchParams({
            page: String(view === 'tree' ? 1 : page),
            limit: String(limit),
            search, country, from, to, activity, sortBy, sortDir,
        })
        if (view === 'tree') params.set('all', 'true')
        authedFetch(token, `/api/admin/referrals/organization?${params.toString()}`)
            .then(res => res.json())
            .then(json => {
                if (json.success) {
                    setRows(json.data.rows)
                    setTotal(json.data.total)
                } else setError(json.error || 'Failed to load organization data')
            })
            .catch(e => setError(e.message))
            .finally(() => setLoading(false))
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [ready, token, view, page, search, country, from, to, activity, sortBy, sortDir])

    const tree = useMemo(() => {
        if (view !== 'tree') return []
        const roots = rows.filter(r => r.level <= 1)
        const byParent = new Map<string, OrgRow[]>()
        for (const r of rows) {
            if (r.level === 2 && r.referred_by) {
                byParent.set(r.referred_by, [...(byParent.get(r.referred_by) || []), r])
            }
        }
        return roots.map(r => ({ ...r, children: byParent.get(r.id) || [] }))
    }, [rows, view])

    return (
        <div className="space-y-4">
            <div className="flex flex-wrap items-center gap-2 justify-between">
                <div className="flex gap-2">
                    <button
                        className={`px-3 py-1.5 rounded text-sm ${view === 'table' ? 'bg-indigo-600' : 'bg-gray-800'}`}
                        onClick={() => setView('table')}
                    >Table View</button>
                    <button
                        className={`px-3 py-1.5 rounded text-sm ${view === 'tree' ? 'bg-indigo-600' : 'bg-gray-800'}`}
                        onClick={() => setView('tree')}
                    >Tree View</button>
                </div>
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-3 lg:grid-cols-6 gap-2">
                <input
                    className="bg-gray-900 border border-gray-700 rounded px-3 py-2 text-sm sm:col-span-2"
                    placeholder="Search name / email / referral code"
                    value={search}
                    onChange={e => { setPage(1); setSearch(e.target.value) }}
                />
                <input
                    className="bg-gray-900 border border-gray-700 rounded px-3 py-2 text-sm"
                    placeholder="Country (e.g. KR)"
                    value={country}
                    onChange={e => { setPage(1); setCountry(e.target.value.toUpperCase()) }}
                />
                <input type="date" className="bg-gray-900 border border-gray-700 rounded px-3 py-2 text-sm"
                    value={from} onChange={e => { setPage(1); setFrom(e.target.value) }} />
                <input type="date" className="bg-gray-900 border border-gray-700 rounded px-3 py-2 text-sm"
                    value={to} onChange={e => { setPage(1); setTo(e.target.value) }} />
                <select className="bg-gray-900 border border-gray-700 rounded px-3 py-2 text-sm"
                    value={activity} onChange={e => { setPage(1); setActivity(e.target.value) }}>
                    <option value="all">All activity</option>
                    <option value="active">Active (has commission)</option>
                    <option value="inactive">Inactive</option>
                </select>
            </div>

            {view === 'table' && (
                <div className="flex gap-2 text-sm">
                    <span className="text-gray-400 py-1">Sort:</span>
                    {[['created_at', 'Signup'], ['referrals', 'Referral Count'], ['commission', 'Commission']].map(([key, label]) => (
                        <button key={key}
                            className={`px-2 py-1 rounded ${sortBy === key ? 'bg-indigo-600' : 'bg-gray-800'}`}
                            onClick={() => setSortBy(key)}
                        >{label}</button>
                    ))}
                    <button className="px-2 py-1 rounded bg-gray-800" onClick={() => setSortDir(d => d === 'asc' ? 'desc' : 'asc')}>
                        {sortDir === 'asc' ? '↑ Asc' : '↓ Desc'}
                    </button>
                </div>
            )}

            {(!ready || loading) && <LoadingBlock />}
            {error && <ErrorBlock message={error} />}

            {ready && !loading && !error && view === 'table' && (
                rows.length === 0 ? <EmptyBlock /> : (
                    <div className="overflow-x-auto border border-gray-800 rounded-xl">
                        <table className="w-full text-sm">
                            <thead className="bg-gray-900 text-gray-400 text-xs uppercase">
                                <tr>
                                    <th className="px-3 py-2 text-left">Member</th>
                                    <th className="px-3 py-2 text-left">Level</th>
                                    <th className="px-3 py-2 text-left">Sponsor</th>
                                    <th className="px-3 py-2 text-left">Country</th>
                                    <th className="px-3 py-2 text-left">Signup</th>
                                    <th className="px-3 py-2 text-right">Referrals</th>
                                    <th className="px-3 py-2 text-right">Commission</th>
                                </tr>
                            </thead>
                            <tbody>
                                {rows.map(r => (
                                    <tr key={r.id} className="border-t border-gray-800 hover:bg-gray-900/60">
                                        <td className="px-3 py-2">
                                            <Link href={`/admin/referrals/members/${r.id}`} className="text-indigo-400 hover:underline">
                                                {r.full_name || r.email}
                                            </Link>
                                            <div className="text-xs text-gray-500">{r.referral_code || '-'}</div>
                                        </td>
                                        <td className="px-3 py-2">{r.level || '-'}</td>
                                        <td className="px-3 py-2">{r.sponsor_name || '-'}</td>
                                        <td className="px-3 py-2">{r.country || '-'}</td>
                                        <td className="px-3 py-2">{formatDate(r.created_at)}</td>
                                        <td className="px-3 py-2 text-right">{r.direct_referrals}</td>
                                        <td className="px-3 py-2 text-right">${formatUsd(r.commission_total)}</td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    </div>
                )
            )}

            {ready && !loading && !error && view === 'table' && (
                <Pagination page={page} limit={limit} total={total} onPage={setPage} />
            )}

            {ready && !loading && !error && view === 'tree' && (
                tree.length === 0 ? <EmptyBlock /> : (
                    <div className="overflow-x-auto rounded-2xl border border-gray-800 bg-gray-950/40 p-6">
                        <div className="flex flex-wrap gap-x-10 gap-y-8">
                            {tree.map(root => (
                                <div key={root.id} className="flex flex-col items-center">
                                    <OrgMemberCard row={root} isRoot />
                                    {root.children.length > 0 && (
                                        <div className="flex flex-col items-center">
                                            <div className="h-6 w-px bg-gray-700" />
                                            <div className="flex gap-5 border-t border-gray-700 pt-6">
                                                {root.children.map(child => (
                                                    <div key={child.id} className="relative">
                                                        <div className="absolute -top-6 left-1/2 h-6 w-px -translate-x-1/2 bg-gray-700" />
                                                        <OrgMemberCard row={child} />
                                                    </div>
                                                ))}
                                            </div>
                                        </div>
                                    )}
                                </div>
                            ))}
                        </div>
                    </div>
                )
            )}
        </div>
    )
}
