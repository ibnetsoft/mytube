import { NextResponse } from 'next/server'
import { isAuthResponse, requireAdmin } from '../../../_auth'
import { getAdmin } from '../../_shared'

export const dynamic = 'force-dynamic'

export async function GET(req: Request, { params }: { params: { id: string } }) {
    try {
        const requester = await requireAdmin(req)
        if (isAuthResponse(requester)) return requester

        const userId = params.id
        if (!userId) return NextResponse.json({ success: false, error: 'Missing member id' }, { status: 400 })

        const supabase = getAdmin()

        const { data: profile, error: profileError } = await supabase
            .from('profiles')
            .select('id, email, full_name, referral_code, my_referral_code, referred_by, referral_country, country_code, created_at, usdt_balance, wallet_address')
            .eq('id', userId)
            .single()
        if (profileError || !profile) {
            return NextResponse.json({ success: false, error: 'Member not found' }, { status: 404 })
        }

        const sponsorPromise = profile.referred_by
            ? supabase.from('profiles').select('id, email, full_name').eq('id', profile.referred_by).maybeSingle()
            : Promise.resolve({ data: null, error: null } as any)

        const l1Promise = supabase
            .from('profiles')
            .select('id, email, full_name, created_at')
            .eq('referred_by', userId)

        const commissionsPromise = supabase
            .from('referral_commissions')
            .select('id, source_user_id, commission_level, source_job_id, base_tokens, rate_percent, commission_tokens, commission_type, status, created_at, paid_at')
            .eq('beneficiary_id', userId)
            .order('created_at', { ascending: false })

        const withdrawalsPromise = supabase
            .from('referral_withdrawals')
            .select('id, amount, status, wallet_address, requested_at, approved_at, sent_at, completed_at, rejected_at, tx_hash, reason')
            .eq('user_id', userId)
            .order('requested_at', { ascending: false })

        const jobsPromise = supabase
            .from('publishing_requests')
            .select('id, status, created_at, metadata')
            .eq('user_id', userId)
            .order('created_at', { ascending: false })
            .limit(20)

        const [sponsorRes, l1Res, commissionsRes, withdrawalsRes, jobsRes] = await Promise.all([
            sponsorPromise, l1Promise, commissionsPromise, withdrawalsPromise, jobsPromise,
        ])

        if (l1Res.error) throw l1Res.error
        if (commissionsRes.error) throw commissionsRes.error
        if (withdrawalsRes.error) throw withdrawalsRes.error
        if (jobsRes.error) throw jobsRes.error

        const l1Members = l1Res.data || []
        const l1Ids = l1Members.map((m: any) => m.id)

        let l2Members: any[] = []
        if (l1Ids.length > 0) {
            const { data: l2Data, error: l2Error } = await supabase
                .from('profiles')
                .select('id, email, full_name, created_at, referred_by')
                .in('referred_by', l1Ids)
            if (l2Error) throw l2Error
            l2Members = l2Data || []
        }

        const commissions = commissionsRes.data || []
        const paidNonWithdrawal = commissions.filter((c: any) => c.commission_type !== 'WITHDRAWAL' && String(c.status || '').toLowerCase() === 'paid')

        const now = new Date()
        const monthStart = new Date(now.getFullYear(), now.getMonth(), 1)
        const sum = (rows: any[]) => rows.reduce((acc, r) => acc + (Number(r.commission_tokens) || 0), 0)

        const cumulativeCommission = sum(paidNonWithdrawal)
        const thisMonthCommission = sum(paidNonWithdrawal.filter((c: any) => new Date(c.created_at) >= monthStart))

        const jobs = jobsRes.data || []
        const approvedJobs = jobs.filter((j: any) => j.status === 'approved')
        const thisMonthJobs = approvedJobs.filter((j: any) => new Date(j.created_at) >= monthStart).length

        const withdrawals = withdrawalsRes.data || []
        const inFlightOrDone = new Set(['REQUESTED', 'APPROVED', 'SENDING', 'COMPLETED'])
        const totalWithdrawn = withdrawals
            .filter((w: any) => inFlightOrDone.has(w.status))
            .reduce((acc: number, w: any) => acc + (Number(w.amount) || 0), 0)
        const availableBalance = Math.max(0, cumulativeCommission - totalWithdrawn)

        return NextResponse.json({
            success: true,
            data: {
                profile: {
                    id: profile.id,
                    email: profile.email,
                    full_name: profile.full_name,
                    referral_code: profile.referral_code || profile.my_referral_code || null,
                    country: profile.referral_country || profile.country_code || null,
                    created_at: profile.created_at,
                    wallet_address: profile.wallet_address,
                },
                sponsor: (sponsorRes as any)?.data || null,
                level1: l1Members,
                level2: l2Members,
                stats: {
                    thisMonthJobs,
                    cumulativeJobs: approvedJobs.length,
                    thisMonthCommission,
                    cumulativeCommission,
                    availableBalance,
                },
                withdrawalHistory: withdrawals,
                recentJobs: jobs.slice(0, 10),
                commissions,
            },
        })
    } catch (error: any) {
        console.error('[Referral Member Detail API] error:', error)
        return NextResponse.json({ success: false, error: error.message }, { status: 500 })
    }
}
