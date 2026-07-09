import { NextResponse } from 'next/server'
import { isAuthResponse, requireAdmin } from '../../_auth'
import { getAdmin, parsePagination, scopedCountry, matchesCountryScope } from '../_shared'

export const dynamic = 'force-dynamic'

// AIR-0223 Organization endpoint. Returns the 2-level referral org, scoped by
// country for country managers, with search/filter/sort applied server-side
// and pagination for Table view. Tree view (?all=true) gets the full scoped
// set (capped) since a tree needs every node to nest correctly, not a page
// of them.
export async function GET(req: Request) {
    try {
        const requester = await requireAdmin(req)
        if (isAuthResponse(requester)) return requester

        const { searchParams } = new URL(req.url)
        const search = (searchParams.get('search') || '').trim()
        const countryFilter = (searchParams.get('country') || '').trim().toUpperCase()
        const fromDate = searchParams.get('from') || ''
        const toDate = searchParams.get('to') || ''
        const activity = (searchParams.get('activity') || 'all').toLowerCase() // all | active | inactive
        const sortBy = (searchParams.get('sortBy') || 'created_at') as 'created_at' | 'referrals' | 'commission'
        const sortDir = (searchParams.get('sortDir') || 'desc') as 'asc' | 'desc'
        const fetchAll = searchParams.get('all') === 'true'
        const { page, limit, offset } = parsePagination(searchParams, 20, 100)

        const supabase = getAdmin()

        let query = supabase
            .from('profiles')
            .select('id, email, full_name, referral_code, my_referral_code, referred_by, referral_country, country_code, created_at')

        if (search) {
            const s = search.replace(/[%,]/g, '')
            query = query.or(
                `email.ilike.*${s}*,full_name.ilike.*${s}*,referral_code.ilike.*${s}*,my_referral_code.ilike.*${s}*`
            )
        }
        if (fromDate) query = query.gte('created_at', fromDate)
        if (toDate) query = query.lte('created_at', toDate)

        const { data: profiles, error: profilesError } = await query
        if (profilesError) throw profilesError

        const scope = scopedCountry(requester)
        let visible = (profiles || []).filter((p: any) => matchesCountryScope(p, scope))
        if (countryFilter) {
            visible = visible.filter((p: any) =>
                String(p.referral_country || p.country_code || '').toUpperCase() === countryFilter
            )
        }

        const byId = new Map(visible.map((p: any) => [p.id, p]))
        const childrenByParent = new Map<string, any[]>()
        for (const p of visible) {
            if (!p.referred_by) continue
            childrenByParent.set(p.referred_by, [...(childrenByParent.get(p.referred_by) || []), p])
        }

        const { data: commissions, error: commissionsError } = await supabase
            .from('referral_commissions')
            .select('beneficiary_id, commission_level, commission_tokens, commission_type, status')
        if (commissionsError) throw commissionsError

        const paidByBeneficiary = new Map<string, { total: number; l1: number; l2: number; count: number }>()
        for (const c of commissions || []) {
            if (c.commission_type === 'WITHDRAWAL') continue
            if (String(c.status || '').toLowerCase() !== 'paid') continue
            const entry = paidByBeneficiary.get(c.beneficiary_id) || { total: 0, l1: 0, l2: 0, count: 0 }
            const amount = Number(c.commission_tokens) || 0
            entry.total += amount
            entry.count += 1
            if (c.commission_level === 1) entry.l1 += amount
            else if (c.commission_level === 2) entry.l2 += amount
            paidByBeneficiary.set(c.beneficiary_id, entry)
        }

        let rows = visible.map((p: any) => {
            const sponsor = p.referred_by ? byId.get(p.referred_by) : null
            const level = !p.referred_by ? 0 : (sponsor?.referred_by && byId.has(sponsor.referred_by) ? 2 : 1)
            const stats = paidByBeneficiary.get(p.id) || { total: 0, l1: 0, l2: 0, count: 0 }
            const directReferrals = (childrenByParent.get(p.id) || []).length
            return {
                id: p.id,
                email: p.email,
                full_name: p.full_name,
                referral_code: p.referral_code || p.my_referral_code || null,
                referred_by: p.referred_by,
                sponsor_name: sponsor?.full_name || sponsor?.email || null,
                country: p.referral_country || p.country_code || null,
                created_at: p.created_at,
                level,
                direct_referrals: directReferrals,
                commission_total: stats.total,
                commission_level1_total: stats.l1,
                commission_level2_total: stats.l2,
                is_active: stats.count > 0,
            }
        })

        if (activity === 'active') rows = rows.filter((r: any) => r.is_active)
        else if (activity === 'inactive') rows = rows.filter((r: any) => !r.is_active)

        rows.sort((a: any, b: any) => {
            let cmp = 0
            if (sortBy === 'referrals') cmp = a.direct_referrals - b.direct_referrals
            else if (sortBy === 'commission') cmp = a.commission_total - b.commission_total
            else cmp = new Date(a.created_at).getTime() - new Date(b.created_at).getTime()
            return sortDir === 'asc' ? cmp : -cmp
        })

        const total = rows.length
        const pageRows = fetchAll ? rows.slice(0, 2000) : rows.slice(offset, offset + limit)

        return NextResponse.json({
            success: true,
            data: {
                rows: pageRows,
                total,
                page,
                limit,
            },
        })
    } catch (error: any) {
        console.error('[Referral Organization API] error:', error)
        return NextResponse.json({ success: false, error: error.message }, { status: 500 })
    }
}
