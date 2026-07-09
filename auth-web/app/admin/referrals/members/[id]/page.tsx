'use client'

import { useEffect, useState } from 'react'
import { useParams } from 'next/navigation'
import Link from 'next/link'
import { useAuthToken, authedFetch, formatUsd, formatDate } from '../../_hooks'
import { LoadingBlock, ErrorBlock, Card, StatusBadge, EmptyBlock } from '../../_components'

export default function MemberDetailPage() {
    const params = useParams()
    const id = params?.id as string
    const { token, ready } = useAuthToken()
    const [data, setData] = useState<any>(null)
    const [loading, setLoading] = useState(true)
    const [error, setError] = useState('')

    useEffect(() => {
        if (!ready || !id) return
        setLoading(true)
        authedFetch(token, `/api/admin/referrals/members/${id}`)
            .then(res => res.json())
            .then(json => {
                if (json.success) setData(json.data)
                else setError(json.error || 'Failed to load member')
            })
            .catch(e => setError(e.message))
            .finally(() => setLoading(false))
    }, [ready, token, id])

    if (!ready || loading) return <LoadingBlock />
    if (error) return <ErrorBlock message={error} />
    if (!data) return null

    const { profile, sponsor, level1, level2, stats, withdrawalHistory, recentJobs } = data

    return (
        <div className="space-y-6">
            <Card>
                <div className="flex flex-wrap justify-between gap-4">
                    <div>
                        <div className="text-2xl font-bold">{profile.full_name || profile.email}</div>
                        <div className="text-gray-400 text-sm">{profile.email}</div>
                    </div>
                    <div className="text-sm text-gray-400 space-y-1">
                        <div>Referral Code: <span className="text-white font-mono">{profile.referral_code || '-'}</span></div>
                        <div>Country: <span className="text-white">{profile.country || '-'}</span></div>
                        <div>Signed up: <span className="text-white">{formatDate(profile.created_at)}</span></div>
                        <div>Referrer: {sponsor
                            ? <Link href={`/admin/referrals/members/${sponsor.id}`} className="text-indigo-400 hover:underline">{sponsor.full_name || sponsor.email}</Link>
                            : <span className="text-white">None (organic / default sponsor)</span>}
                        </div>
                    </div>
                </div>
            </Card>

            <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                <Card><div className="text-xs text-gray-400">This Month Jobs</div><div className="text-xl font-bold">{stats.thisMonthJobs}</div></Card>
                <Card><div className="text-xs text-gray-400">Cumulative Jobs</div><div className="text-xl font-bold">{stats.cumulativeJobs}</div></Card>
                <Card><div className="text-xs text-gray-400">This Month Commission</div><div className="text-xl font-bold">${formatUsd(stats.thisMonthCommission)}</div></Card>
                <Card><div className="text-xs text-gray-400">Cumulative Commission</div><div className="text-xl font-bold">${formatUsd(stats.cumulativeCommission)}</div></Card>
                <Card className="col-span-2 md:col-span-4"><div className="text-xs text-gray-400">Available Withdrawal Balance</div><div className="text-2xl font-bold text-green-400">${formatUsd(stats.availableBalance)}</div></Card>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <Card>
                    <div className="font-semibold mb-2">Level 1 ({level1.length})</div>
                    {level1.length === 0 ? <EmptyBlock label="No direct referrals." /> : (
                        <ul className="text-sm space-y-1 max-h-64 overflow-y-auto">
                            {level1.map((m: any) => (
                                <li key={m.id}>
                                    <Link href={`/admin/referrals/members/${m.id}`} className="text-indigo-400 hover:underline">{m.full_name || m.email}</Link>
                                </li>
                            ))}
                        </ul>
                    )}
                </Card>
                <Card>
                    <div className="font-semibold mb-2">Level 2 ({level2.length})</div>
                    {level2.length === 0 ? <EmptyBlock label="No level-2 referrals." /> : (
                        <ul className="text-sm space-y-1 max-h-64 overflow-y-auto">
                            {level2.map((m: any) => (
                                <li key={m.id}>
                                    <Link href={`/admin/referrals/members/${m.id}`} className="text-indigo-400 hover:underline">{m.full_name || m.email}</Link>
                                </li>
                            ))}
                        </ul>
                    )}
                </Card>
            </div>

            <Card>
                <div className="font-semibold mb-2">Withdrawal History</div>
                {withdrawalHistory.length === 0 ? <EmptyBlock label="No withdrawal requests." /> : (
                    <div className="overflow-x-auto">
                        <table className="w-full text-sm">
                            <thead className="text-gray-400 text-xs uppercase">
                                <tr><th className="text-left py-1">Requested</th><th className="text-left py-1">Amount</th><th className="text-left py-1">Status</th></tr>
                            </thead>
                            <tbody>
                                {withdrawalHistory.map((w: any) => (
                                    <tr key={w.id} className="border-t border-gray-800">
                                        <td className="py-1.5">{formatDate(w.requested_at)}</td>
                                        <td className="py-1.5">${formatUsd(w.amount)}</td>
                                        <td className="py-1.5"><StatusBadge status={w.status} /></td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    </div>
                )}
            </Card>

            <Card>
                <div className="font-semibold mb-2">Recent Jobs</div>
                {recentJobs.length === 0 ? <EmptyBlock label="No jobs found." /> : (
                    <ul className="text-sm space-y-1">
                        {recentJobs.map((j: any) => (
                            <li key={j.id} className="flex justify-between border-t border-gray-800 py-1.5">
                                <span>{j.metadata?.title || j.id}</span>
                                <span className="flex items-center gap-2 text-gray-400">
                                    {formatDate(j.created_at)} <StatusBadge status={j.status} />
                                </span>
                            </li>
                        ))}
                    </ul>
                )}
            </Card>
        </div>
    )
}
