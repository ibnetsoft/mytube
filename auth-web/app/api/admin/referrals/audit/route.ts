import { NextResponse } from 'next/server'
import { isAuthResponse, requireAdmin } from '../../_auth'
import { getAdmin, parsePagination } from '../_shared'

export const dynamic = 'force-dynamic'

// AIR-0223 Audit viewer. Pure read of referral_audit_logs — the writes
// already happen from AIR-0221 Stage 2 (settlement/withdrawal request paths)
// and this ticket's own withdrawals/[id]/route.ts. No write path here.
export async function GET(req: Request) {
    try {
        const requester = await requireAdmin(req)
        if (isAuthResponse(requester)) return requester

        const { searchParams } = new URL(req.url)
        const entityType = searchParams.get('entityType') // 'commission' | 'withdrawal' | null
        const action = searchParams.get('action') // generated|requested|approved|rejected|sending|completed|reversed
        const fromDate = searchParams.get('from') || ''
        const toDate = searchParams.get('to') || ''
        const adminSearch = (searchParams.get('admin') || '').trim()
        const memberSearch = (searchParams.get('member') || '').trim()
        const { page, limit, offset } = parsePagination(searchParams, 25, 200)

        const supabase = getAdmin()

        let actorIds: string[] | null = null
        if (adminSearch) {
            const s = adminSearch.replace(/[%,]/g, '')
            const { data: matches, error: matchError } = await supabase
                .from('profiles').select('id').or(`email.ilike.*${s}*,full_name.ilike.*${s}*`)
            if (matchError) throw matchError
            actorIds = (matches || []).map((m: any) => m.id)
            if (actorIds.length === 0) {
                return NextResponse.json({ success: true, data: { rows: [], total: 0, page, limit } })
            }
        }

        let query = supabase.from('referral_audit_logs').select('*', { count: 'exact' })

        if (entityType) query = query.eq('entity_type', entityType)
        if (action) query = query.eq('action', action)
        if (fromDate) query = query.gte('created_at', fromDate)
        if (toDate) query = query.lte('created_at', toDate)
        if (actorIds) query = query.in('actor_id', actorIds)

        query = query.order('created_at', { ascending: false }).range(offset, offset + limit - 1)

        const { data: rows, count, error } = await query
        if (error) throw error

        let filtered = rows || []
        // Member search: resolve entity_id → referral_withdrawals.user_id when
        // entity_type='withdrawal', post-filter in-memory (no FK on entity_id
        // to join server-side).
        if (memberSearch) {
            const s = memberSearch.toLowerCase()
            const withdrawalIds = filtered.filter((r: any) => r.entity_type === 'withdrawal').map((r: any) => r.entity_id)
            let memberByWithdrawal = new Map<string, any>()
            if (withdrawalIds.length > 0) {
                const { data: withdrawalRows } = await supabase
                    .from('referral_withdrawals')
                    .select('id, user_id')
                    .in('id', withdrawalIds)
                const userIds = Array.from(new Set((withdrawalRows || []).map((w: any) => w.user_id)))
                const { data: profiles } = await supabase.from('profiles').select('id, email, full_name').in('id', userIds)
                const profileMap = new Map((profiles || []).map((p: any) => [p.id, p]))
                memberByWithdrawal = new Map(
                    (withdrawalRows || []).map((w: any) => [w.id, profileMap.get(w.user_id) || null])
                )
            }
            filtered = filtered.filter((r: any) => {
                const member = r.entity_type === 'withdrawal' ? memberByWithdrawal.get(r.entity_id) : null
                const haystack = `${member?.email || ''} ${member?.full_name || ''}`.toLowerCase()
                return haystack.includes(s)
            })
        }

        const actorIdsInPage = Array.from(new Set(filtered.map((r: any) => r.actor_id).filter(Boolean)))
        let actorMap = new Map<string, any>()
        if (actorIdsInPage.length > 0) {
            const { data: actors } = await supabase.from('profiles').select('id, email, full_name').in('id', actorIdsInPage)
            actorMap = new Map((actors || []).map((a: any) => [a.id, a]))
        }

        const enriched = filtered.map((r: any) => ({ ...r, actor: r.actor_id ? actorMap.get(r.actor_id) || null : null }))

        return NextResponse.json({ success: true, data: { rows: enriched, total: count || 0, page, limit } })
    } catch (error: any) {
        console.error('[Referral Audit API] error:', error)
        return NextResponse.json({ success: false, error: error.message }, { status: 500 })
    }
}
