import { NextResponse } from 'next/server'
import { isAuthResponse, requireAdmin } from '../../_auth'
import { getAdmin, scopedCountry, matchesCountryScope, displayName } from '../_shared'

export const dynamic = 'force-dynamic'

export async function GET(req: Request) {
    try {
        const requester = await requireAdmin(req)
        if (isAuthResponse(requester)) return requester

        const supabase = getAdmin()
        const scope = scopedCountry(requester)

        const { data: profiles, error: profilesError } = await supabase
            .from('profiles')
            .select('id, email, full_name, referred_by, referral_country, country_code, created_at')
        if (profilesError) throw profilesError

        const visible = (profiles || []).filter((p: any) => matchesCountryScope(p, scope))
        const visibleIds = new Set(visible.map((p: any) => p.id))
        const byId = new Map(visible.map((p: any) => [p.id, p]))

        let level1Count = 0
        let level2Count = 0
        for (const p of visible) {
            if (!p.referred_by || !byId.has(p.referred_by)) continue
            level1Count += 1
            const sponsor = byId.get(p.referred_by)
            if (sponsor?.referred_by && byId.has(sponsor.referred_by)) {
                level2Count += 1
            }
        }

        // referral_commissions: real ledger (AIR-0221 Stage 1/2 data model)
        const { data: commissions, error: commissionsError } = await supabase
            .from('referral_commissions')
            .select('beneficiary_id, source_user_id, commission_tokens, commission_type, status, created_at')
        if (commissionsError) throw commissionsError

        const visibleCommissions = (commissions || []).filter((c: any) =>
            visibleIds.has(c.beneficiary_id) && c.commission_type !== 'WITHDRAWAL'
        )
        const paidCommissions = visibleCommissions.filter((c: any) => String(c.status || '').toLowerCase() === 'paid')

        const now = new Date()
        const todayStart = new Date(now.getFullYear(), now.getMonth(), now.getDate())
        const monthStart = new Date(now.getFullYear(), now.getMonth(), 1)

        const sum = (rows: any[]) => rows.reduce((acc, r) => acc + (Number(r.commission_tokens) || 0), 0)

        const todaysCommission = sum(paidCommissions.filter((c: any) => new Date(c.created_at) >= todayStart))
        const monthlyCommission = sum(paidCommissions.filter((c: any) => new Date(c.created_at) >= monthStart))
        const totalPaidCommission = sum(paidCommissions)

        // Top sponsor (by total paid commission)
        const bySponsor = new Map<string, number>()
        for (const c of paidCommissions) {
            bySponsor.set(c.beneficiary_id, (bySponsor.get(c.beneficiary_id) || 0) + (Number(c.commission_tokens) || 0))
        }
        let topSponsor: { id: string; name: string; total: number } | null = null
        for (const [id, total] of bySponsor.entries()) {
            if (!topSponsor || total > topSponsor.total) {
                topSponsor = { id, name: displayName(byId.get(id)), total }
            }
        }

        // Top country (by referred-member count)
        const byCountry = new Map<string, number>()
        for (const p of visible) {
            if (!p.referred_by) continue
            const country = String(p.referral_country || p.country_code || 'Unknown').toUpperCase()
            byCountry.set(country, (byCountry.get(country) || 0) + 1)
        }
        let topCountry: { country: string; count: number } | null = null
        for (const [country, count] of byCountry.entries()) {
            if (!topCountry || count > topCountry.count) topCountry = { country, count }
        }

        // Top worker (source_user_id whose activity generated the most commission)
        const byWorker = new Map<string, number>()
        for (const c of paidCommissions) {
            if (!c.source_user_id) continue
            byWorker.set(c.source_user_id, (byWorker.get(c.source_user_id) || 0) + (Number(c.commission_tokens) || 0))
        }
        let topWorker: { id: string; name: string; total: number } | null = null
        for (const [id, total] of byWorker.entries()) {
            if (!topWorker || total > topWorker.total) {
                topWorker = { id, name: displayName(byId.get(id)), total }
            }
        }

        // referral_withdrawals: canonical mirror table (AIR-0221 Stage 1/2)
        const { data: withdrawals, error: withdrawalsError } = await supabase
            .from('referral_withdrawals')
            .select('user_id, amount, status')
        if (withdrawalsError) throw withdrawalsError

        const visibleWithdrawals = (withdrawals || []).filter((w: any) => visibleIds.has(w.user_id))
        const requestedStatuses = new Set(['REQUESTED', 'APPROVED', 'SENDING'])
        const totalWithdrawalRequested = sum(
            visibleWithdrawals.filter((w: any) => requestedStatuses.has(w.status)).map((w: any) => ({ commission_tokens: w.amount }))
        )
        const totalWithdrawalCompleted = sum(
            visibleWithdrawals.filter((w: any) => w.status === 'COMPLETED').map((w: any) => ({ commission_tokens: w.amount }))
        )

        return NextResponse.json({
            success: true,
            data: {
                totalReferralMembers: level1Count + level2Count,
                level1Members: level1Count,
                level2Members: level2Count,
                todaysCommission,
                monthlyCommission,
                totalPaidCommission,
                totalWithdrawalRequested,
                totalWithdrawalCompleted,
                topSponsor,
                topCountry,
                topWorker,
            },
        })
    } catch (error: any) {
        console.error('[Referral Dashboard API] error:', error)
        return NextResponse.json({ success: false, error: error.message }, { status: 500 })
    }
}
