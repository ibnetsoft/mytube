import { createClient } from '@supabase/supabase-js'
import { NextResponse } from 'next/server'

export const dynamic = 'force-dynamic'

const getAdmin = () => createClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.SUPABASE_SERVICE_ROLE_KEY!,
    { auth: { persistSession: false } }
)

const getAuthClient = () => createClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!,
    { auth: { persistSession: false, autoRefreshToken: false } }
)

function tokenTotal(row: any) {
    return Number(row?.input_tokens || 0) + Number(row?.output_tokens || 0) + Number(row?.thinking_tokens || 0)
}

export async function GET(req: Request) {
    try {
        const authHeader = req.headers.get('authorization') || ''
        const token = authHeader.toLowerCase().startsWith('bearer ') ? authHeader.slice(7).trim() : ''
        if (!token) return NextResponse.json({ error: 'Login required' }, { status: 401 })

        const { data: authData, error: authError } = await getAuthClient().auth.getUser(token)
        const user = authData.user
        if (authError || !user) return NextResponse.json({ error: 'Login required' }, { status: 401 })

        const supabase = getAdmin()
        const { data: profile, error: profileError } = await supabase
            .from('profiles')
            .select('id, email, referral_code, referred_by, referral_depth, country_code, referral_country, commission_rate')
            .eq('id', user.id)
            .maybeSingle()
        if (profileError) throw profileError

        const { data: directReferrals, error: directError } = await supabase
            .from('profiles')
            .select('id, email, full_name, referral_code, referral_country, country_code, created_at')
            .eq('referred_by', user.id)
            .order('created_at', { ascending: false })
        if (directError) throw directError

        const directIds = (directReferrals || []).map((item: any) => item.id)

        // AIR-0225: per-member commission I've earned from each direct
        // referral's activity, so the card view can show it without a
        // separate detail-page click.
        const commissionBySource = new Map<string, number>()
        if (directIds.length) {
            const { data: commissionRows, error: commissionError } = await supabase
                .from('referral_commissions')
                .select('source_user_id, commission_tokens')
                .eq('beneficiary_id', user.id)
                .in('source_user_id', directIds)
                .neq('commission_type', 'WITHDRAWAL')
            if (!commissionError) {
                for (const row of commissionRows || []) {
                    const prev = commissionBySource.get(row.source_user_id) || 0
                    commissionBySource.set(row.source_user_id, prev + (Number(row.commission_tokens) || 0))
                }
            }
        }

        const directReferralsWithStats = (directReferrals || []).map((item: any) => {
            const earned = commissionBySource.get(item.id) || 0
            return {
                ...item,
                country: item.referral_country || item.country_code || null,
                commission_earned: earned,
                is_active: earned > 0,
            }
        })

        let totalReferralTokens = 0
        if (directIds.length) {
            let { data: logs, error: logsError } = await supabase
                .from('ai_logs')
                .select('user_id, input_tokens, output_tokens, thinking_tokens')
                .in('user_id', directIds)
                .limit(5000)
            if (logsError && (logsError.code === '42P01' || logsError.code === 'PGRST116')) {
                const fallback = await supabase
                    .from('ai_generation_logs')
                    .select('user_id, input_tokens, output_tokens, thinking_tokens')
                    .in('user_id', directIds)
                    .limit(5000)
                logs = fallback.data
                logsError = fallback.error
            }
            if (!logsError) {
                totalReferralTokens = (logs || []).reduce((sum: number, row: any) => sum + tokenTotal(row), 0)
            }
        }

        const code = profile?.referral_code || ''
        const origin = new URL(req.url).origin
        return NextResponse.json({
            profile: profile || null,
            directReferrals: directReferralsWithStats,
            summary: {
                directCount: directReferrals?.length || 0,
                referralTokenUsage: totalReferralTokens,
                estimatedCommissionTokens: Math.round(totalReferralTokens * 0.05),
                referralLink: code ? `${origin}/?ref=${code}` : '',
            },
        })
    } catch (error: any) {
        console.error('Referral API error:', error)
        return NextResponse.json({ error: error.message }, { status: 500 })
    }
}
