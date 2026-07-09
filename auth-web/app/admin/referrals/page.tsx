'use client'

import { useEffect, useState } from 'react'
import { useAuthToken, authedFetch, formatUsd } from './_hooks'
import { LoadingBlock, ErrorBlock, KpiCard, Card } from './_components'

interface DashboardData {
    totalReferralMembers: number
    level1Members: number
    level2Members: number
    todaysCommission: number
    monthlyCommission: number
    totalPaidCommission: number
    totalWithdrawalRequested: number
    totalWithdrawalCompleted: number
    topSponsor: { id: string; name: string; total: number } | null
    topCountry: { country: string; count: number } | null
    topWorker: { id: string; name: string; total: number } | null
}

export default function ReferralDashboardPage() {
    const { token, ready } = useAuthToken()
    const [data, setData] = useState<DashboardData | null>(null)
    const [loading, setLoading] = useState(true)
    const [error, setError] = useState('')

    useEffect(() => {
        if (!ready) return
        setLoading(true)
        authedFetch(token, '/api/admin/referrals/dashboard')
            .then(res => res.json())
            .then(json => {
                if (json.success) setData(json.data)
                else setError(json.error || 'Failed to load dashboard')
            })
            .catch(e => setError(e.message))
            .finally(() => setLoading(false))
    }, [ready, token])

    if (!ready || loading) return <LoadingBlock />
    if (error) return <ErrorBlock message={error} />
    if (!data) return null

    return (
        <div className="space-y-6">
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                <KpiCard label="Total Referral Members" value={String(data.totalReferralMembers)} />
                <KpiCard label="Level 1 Members" value={String(data.level1Members)} />
                <KpiCard label="Level 2 Members" value={String(data.level2Members)} />
                <KpiCard label="Today's Commission" value={`$${formatUsd(data.todaysCommission)}`} />
                <KpiCard label="Monthly Commission" value={`$${formatUsd(data.monthlyCommission)}`} />
                <KpiCard label="Total Paid Commission" value={`$${formatUsd(data.totalPaidCommission)}`} />
                <KpiCard label="Total Withdrawal Requested" value={`$${formatUsd(data.totalWithdrawalRequested)}`} />
                <KpiCard label="Total Withdrawal Completed" value={`$${formatUsd(data.totalWithdrawalCompleted)}`} />
            </div>

            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                <Card>
                    <div className="text-xs uppercase tracking-wide text-gray-400 mb-2">Top Sponsor</div>
                    {data.topSponsor ? (
                        <>
                            <div className="text-lg font-bold">{data.topSponsor.name}</div>
                            <div className="text-sm text-gray-400">${formatUsd(data.topSponsor.total)}</div>
                        </>
                    ) : <div className="text-gray-500 text-sm">No data yet</div>}
                </Card>
                <Card>
                    <div className="text-xs uppercase tracking-wide text-gray-400 mb-2">Top Country</div>
                    {data.topCountry ? (
                        <>
                            <div className="text-lg font-bold">{data.topCountry.country}</div>
                            <div className="text-sm text-gray-400">{data.topCountry.count} members</div>
                        </>
                    ) : <div className="text-gray-500 text-sm">No data yet</div>}
                </Card>
                <Card>
                    <div className="text-xs uppercase tracking-wide text-gray-400 mb-2">Top Worker</div>
                    {data.topWorker ? (
                        <>
                            <div className="text-lg font-bold">{data.topWorker.name}</div>
                            <div className="text-sm text-gray-400">${formatUsd(data.topWorker.total)} generated</div>
                        </>
                    ) : <div className="text-gray-500 text-sm">No data yet</div>}
                </Card>
            </div>

            <div className="text-xs text-gray-600">
                Data source: <code>referral_commissions</code> / <code>referral_withdrawals</code> (AIR-0221 data model). No production referral activity has occurred yet as of AIR-0223 — see <code>AIR-0221D_REFERRAL_ACTIVATION_PLAN.md</code>.
            </div>
        </div>
    )
}
