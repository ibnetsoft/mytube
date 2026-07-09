import { NextResponse } from 'next/server'
import { isAuthResponse, requireAdmin } from '../../_auth'
import { getAdmin, parsePagination } from '../_shared'

export const dynamic = 'force-dynamic'

// AIR-0223 Commission list. Reads referral_commissions directly (the AIR-0221
// data model) — not the legacy token-usage estimate in /api/admin/referrals.
export async function GET(req: Request) {
    try {
        const requester = await requireAdmin(req)
        if (isAuthResponse(requester)) return requester

        const { searchParams } = new URL(req.url)
        const level = searchParams.get('level') // '1' | '2' | null
        const fromDate = searchParams.get('from') || ''
        const toDate = searchParams.get('to') || ''
        const memberSearch = (searchParams.get('member') || '').trim()
        const sortDir = (searchParams.get('sortDir') || 'desc') as 'asc' | 'desc'
        const { page, limit, offset } = parsePagination(searchParams, 25, 200)

        const supabase = getAdmin()

        let memberIds: string[] | null = null
        if (memberSearch) {
            const s = memberSearch.replace(/[%,]/g, '')
            const { data: matches, error: matchError } = await supabase
                .from('profiles')
                .select('id')
                .or(`email.ilike.*${s}*,full_name.ilike.*${s}*,referral_code.ilike.*${s}*,my_referral_code.ilike.*${s}*`)
            if (matchError) throw matchError
            memberIds = (matches || []).map((m: any) => m.id)
            if (memberIds.length === 0) {
                return NextResponse.json({ success: true, data: { rows: [], total: 0, page, limit } })
            }
        }

        let query = supabase
            .from('referral_commissions')
            .select(
                'id, beneficiary_id, source_user_id, commission_level, source_job_id, base_tokens, rate_percent, commission_tokens, commission_type, status, created_at, paid_at',
                { count: 'exact' }
            )
            .neq('commission_type', 'WITHDRAWAL')

        if (level === '1' || level === '2') query = query.eq('commission_level', Number(level))
        if (fromDate) query = query.gte('created_at', fromDate)
        if (toDate) query = query.lte('created_at', toDate)
        if (memberIds) query = query.in('beneficiary_id', memberIds)

        query = query.order('created_at', { ascending: sortDir === 'asc' }).range(offset, offset + limit - 1)

        const { data: rows, count, error } = await query
        if (error) throw error

        const beneficiaryIds = Array.from(new Set((rows || []).map((r: any) => r.beneficiary_id)))
        const sourceIds = Array.from(new Set((rows || []).map((r: any) => r.source_user_id).filter(Boolean)))
        const allIds = Array.from(new Set([...beneficiaryIds, ...sourceIds]))

        let profileMap = new Map<string, any>()
        if (allIds.length > 0) {
            const { data: profiles, error: profilesError } = await supabase
                .from('profiles')
                .select('id, email, full_name')
                .in('id', allIds)
            if (profilesError) throw profilesError
            profileMap = new Map((profiles || []).map((p: any) => [p.id, p]))
        }

        const enriched = (rows || []).map((r: any) => ({
            ...r,
            beneficiary: profileMap.get(r.beneficiary_id) || null,
            source: profileMap.get(r.source_user_id) || null,
        }))

        return NextResponse.json({
            success: true,
            data: { rows: enriched, total: count || 0, page, limit },
        })
    } catch (error: any) {
        console.error('[Referral Commissions API] error:', error)
        return NextResponse.json({ success: false, error: error.message }, { status: 500 })
    }
}
