import { createClient } from '@supabase/supabase-js'
import { NextResponse } from 'next/server'
import { isAuthResponse, requireAdmin, requireSuperAdmin } from '../_auth'

export const dynamic = 'force-dynamic'

const getAdmin = () => createClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.SUPABASE_SERVICE_ROLE_KEY!,
    { auth: { persistSession: false } }
)

function tokenTotal(row: any) {
    return Number(row?.input_tokens || 0) + Number(row?.output_tokens || 0) + Number(row?.thinking_tokens || 0)
}

function estimateCommission(tokens: number, rate: number) {
    return Math.round(tokens * (rate / 100))
}

export async function GET(req: Request) {
    try {
        const requester = await requireAdmin(req)
        if (isAuthResponse(requester)) return requester

        const { searchParams } = new URL(req.url)
        const countryFilter = String(searchParams.get('country') || '').trim().toUpperCase()
        const days = Math.max(1, Math.min(365, Number.parseInt(searchParams.get('days') || '30', 10) || 30))

        const supabase = getAdmin()
        const { data: profiles, error: profilesError } = await supabase
            .from('profiles')
            .select('id, email, full_name, referral_code, referred_by, referral_depth, country_code, referral_country, commission_rate, token_balance, created_at')
            .order('created_at', { ascending: false })

        if (profilesError) throw profilesError

        const requesterProfile = (profiles || []).find((profile: any) => profile.id === requester.user.id)
        const requesterCountry = String(requesterProfile?.referral_country || requesterProfile?.country_code || '').toUpperCase()
        const visibleProfiles = (profiles || []).filter((profile: any) => {
            const profileCountry = String(profile.referral_country || profile.country_code || '').toUpperCase()
            if (countryFilter && profileCountry !== countryFilter) return false
            if (!requester.isSuperAdmin && requesterCountry && profileCountry !== requesterCountry) return false
            return true
        })

        const visibleIds = new Set(visibleProfiles.map((profile: any) => profile.id))
        const since = new Date()
        since.setDate(since.getDate() - days)

        let logs: any[] = []
        let { data: aiLogs, error: logsError } = await supabase
            .from('ai_logs')
            .select('user_id, input_tokens, output_tokens, thinking_tokens, created_at')
            .gte('created_at', since.toISOString())
            .limit(5000)

        if (logsError && (logsError.code === '42P01' || logsError.code === 'PGRST116')) {
            const fallback = await supabase
                .from('ai_generation_logs')
                .select('user_id, input_tokens, output_tokens, thinking_tokens, created_at')
                .gte('created_at', since.toISOString())
                .limit(5000)
            aiLogs = fallback.data
            logsError = fallback.error
        }
        if (!logsError) logs = aiLogs || []

        const tokensByUser = new Map<string, number>()
        for (const log of logs) {
            const userId = String(log.user_id || '')
            if (!visibleIds.has(userId)) continue
            tokensByUser.set(userId, (tokensByUser.get(userId) || 0) + tokenTotal(log))
        }

        const childrenByParent = new Map<string, any[]>()
        for (const profile of visibleProfiles) {
            const parentId = profile.referred_by ? String(profile.referred_by) : ''
            if (!parentId) continue
            childrenByParent.set(parentId, [...(childrenByParent.get(parentId) || []), profile])
        }

        const rows = visibleProfiles.map((profile: any) => {
            const directChildren = childrenByParent.get(profile.id) || []
            const directTokens = directChildren.reduce((sum, child) => sum + (tokensByUser.get(child.id) || 0), 0)
            const level2Children = directChildren.flatMap(child => childrenByParent.get(child.id) || [])
            const level2Tokens = level2Children.reduce((sum, child) => sum + (tokensByUser.get(child.id) || 0), 0)
            const country = profile.referral_country || profile.country_code || 'KR'
            const countryTokens = visibleProfiles
                .filter((item: any) => String(item.referral_country || item.country_code || 'KR').toUpperCase() === String(country).toUpperCase())
                .reduce((sum: number, item: any) => sum + (tokensByUser.get(item.id) || 0), 0)

            return {
                ...profile,
                token_usage: tokensByUser.get(profile.id) || 0,
                direct_referrals: directChildren.length,
                level2_referrals: level2Children.length,
                direct_commission_tokens: estimateCommission(directTokens, 5),
                level2_commission_tokens: estimateCommission(level2Tokens, 2),
                country_commission_tokens: estimateCommission(countryTokens, Number(profile.commission_rate || 0) || 0),
            }
        })

        const totalTokenUsage = rows.reduce((sum, row) => sum + row.token_usage, 0)
        const totalCommissionTokens = rows.reduce((sum, row) => sum + row.direct_commission_tokens + row.level2_commission_tokens + row.country_commission_tokens, 0)

        return NextResponse.json({
            profiles: rows,
            summary: {
                users: rows.length,
                totalTokenUsage,
                totalCommissionTokens,
                countries: Array.from(new Set(rows.map(row => row.referral_country || row.country_code || 'KR'))),
                days,
            },
        })
    } catch (error: any) {
        console.error('Referral admin API error:', error)
        return NextResponse.json({ error: error.message }, { status: 500 })
    }
}

export async function PATCH(req: Request) {
    try {
        const requester = await requireSuperAdmin(req)
        if (isAuthResponse(requester)) return requester

        const { userId, country_code, referral_country, commission_rate, make_country_manager } = await req.json()
        if (!userId) return NextResponse.json({ error: 'Missing userId' }, { status: 400 })

        const normalizedCountry = String(referral_country || country_code || 'KR').trim().toUpperCase().slice(0, 2) || 'KR'
        const supabase = getAdmin()

        const { error: profileError } = await supabase
            .from('profiles')
            .update({
                country_code: String(country_code || normalizedCountry).trim().toUpperCase().slice(0, 2) || normalizedCountry,
                referral_country: normalizedCountry,
                commission_rate: Number(commission_rate || 0),
            })
            .eq('id', userId)
        if (profileError) throw profileError

        if (make_country_manager !== undefined) {
            const { data: { user: existingUser }, error: fetchError } = await supabase.auth.admin.getUserById(userId)
            if (fetchError) throw fetchError
            const appMetadata = existingUser?.app_metadata || {}
            const { error: authError } = await supabase.auth.admin.updateUserById(userId, {
                app_metadata: {
                    ...appMetadata,
                    role: make_country_manager ? 'sub_admin' : appMetadata.role,
                    country_manager: Boolean(make_country_manager),
                    managed_country: normalizedCountry,
                    is_admin: false,
                }
            })
            if (authError) throw authError
        }

        return NextResponse.json({ success: true })
    } catch (error: any) {
        console.error('Referral admin PATCH error:', error)
        return NextResponse.json({ error: error.message }, { status: 500 })
    }
}
