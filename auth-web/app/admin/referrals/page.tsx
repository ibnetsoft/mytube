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
                <KpiCard label="전체 추천인 멤버" value={String(data.totalReferralMembers)} />
                <KpiCard label="1단계 멤버" value={String(data.level1Members)} />
                <KpiCard label="2단계 멤버" value={String(data.level2Members)} />
                <KpiCard label="오늘 커미션" value={`$${formatUsd(data.todaysCommission)}`} />
                <KpiCard label="이번 달 커미션" value={`$${formatUsd(data.monthlyCommission)}`} />
                <KpiCard label="누적 지급 커미션" value={`$${formatUsd(data.totalPaidCommission)}`} />
                <KpiCard label="출금 요청 총액" value={`$${formatUsd(data.totalWithdrawalRequested)}`} />
                <KpiCard label="출금 완료 총액" value={`$${formatUsd(data.totalWithdrawalCompleted)}`} />
            </div>

            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                <Card>
                    <div className="text-xs uppercase tracking-wide text-gray-400 mb-2">최고 추천인</div>
                    {data.topSponsor ? (
                        <>
                            <div className="text-lg font-bold">{data.topSponsor.name}</div>
                            <div className="text-sm text-gray-400">${formatUsd(data.topSponsor.total)}</div>
                        </>
                    ) : <div className="text-gray-500 text-sm">아직 데이터가 없습니다</div>}
                </Card>
                <Card>
                    <div className="text-xs uppercase tracking-wide text-gray-400 mb-2">최다 국가</div>
                    {data.topCountry ? (
                        <>
                            <div className="text-lg font-bold">{data.topCountry.country}</div>
                            <div className="text-sm text-gray-400">{data.topCountry.count}명</div>
                        </>
                    ) : <div className="text-gray-500 text-sm">아직 데이터가 없습니다</div>}
                </Card>
                <Card>
                    <div className="text-xs uppercase tracking-wide text-gray-400 mb-2">최고 작업자</div>
                    {data.topWorker ? (
                        <>
                            <div className="text-lg font-bold">{data.topWorker.name}</div>
                            <div className="text-sm text-gray-400">${formatUsd(data.topWorker.total)} 발생</div>
                        </>
                    ) : <div className="text-gray-500 text-sm">아직 데이터가 없습니다</div>}
                </Card>
            </div>

            <div className="text-xs text-gray-600">
                데이터 출처: <code>referral_commissions</code> / <code>referral_withdrawals</code> (AIR-0221 데이터 모델).
            </div>
        </div>
    )
}
