import { NextResponse } from 'next/server'
import { isAuthResponse, requireAdmin } from '../../_auth'
import { getAdmin, parsePagination } from '../_shared'

export const dynamic = 'force-dynamic'

// AIR-0223 Withdrawal list. Reads referral_withdrawals directly — the
// canonical mirror table AIR-0221 Stage 2 dual-writes into. Approve/reject
// actions are in withdrawals/[id]/route.ts.
export async function GET(req: Request) {
    try {
        const requester = await requireAdmin(req)
        if (isAuthResponse(requester)) return requester

        const { searchParams } = new URL(req.url)
        const status = searchParams.get('status') // REQUESTED | APPROVED | SENDING | COMPLETED | REJECTED | null
        const fromDate = searchParams.get('from') || ''
        const toDate = searchParams.get('to') || ''
        const memberSearch = (searchParams.get('member') || '').trim()
        const { page, limit, offset } = parsePagination(searchParams, 25, 200)

        const supabase = getAdmin()

        let memberIds: string[] | null = null
        if (memberSearch) {
            const s = memberSearch.replace(/[%,]/g, '')
            const { data: matches, error: matchError } = await supabase
                .from('profiles')
                .select('id')
                .or(`email.ilike.*${s}*,full_name.ilike.*${s}*`)
            if (matchError) throw matchError
            memberIds = (matches || []).map((m: any) => m.id)
            if (memberIds.length === 0) {
                return NextResponse.json({ success: true, data: { rows: [], total: 0, page, limit } })
            }
        }

        let query = supabase
            .from('referral_withdrawals')
            .select('*', { count: 'exact' })

        if (status) query = query.eq('status', status)
        if (fromDate) query = query.gte('requested_at', fromDate)
        if (toDate) query = query.lte('requested_at', toDate)
        if (memberIds) query = query.in('user_id', memberIds)

        query = query.order('requested_at', { ascending: false }).range(offset, offset + limit - 1)

        const { data: rows, count, error } = await query
        if (error) throw error

        const userIds = Array.from(new Set((rows || []).map((r: any) => r.user_id)))
        let profileMap = new Map<string, any>()
        if (userIds.length > 0) {
            const { data: profiles, error: profilesError } = await supabase
                .from('profiles')
                .select('id, email, full_name')
                .in('id', userIds)
            if (profilesError) throw profilesError
            profileMap = new Map((profiles || []).map((p: any) => [p.id, p]))
        }

        const enriched = (rows || []).map((r: any) => ({ ...r, member: profileMap.get(r.user_id) || null }))

        return NextResponse.json({ success: true, data: { rows: enriched, total: count || 0, page, limit } })
    } catch (error: any) {
        console.error('[Referral Withdrawals API] error:', error)
        return NextResponse.json({ success: false, error: error.message }, { status: 500 })
    }
}
