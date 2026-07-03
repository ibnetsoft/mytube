import { createClient } from '@supabase/supabase-js'
import { NextResponse } from 'next/server'
import { isAuthResponse, requireSuperAdmin } from '../../_auth'

export async function GET(req: Request) {
    const requester = await requireSuperAdmin(req)
    if (isAuthResponse(requester)) return requester

    const supabaseUrl = process.env.NEXT_PUBLIC_SUPABASE_URL!
    const supabaseServiceKey = process.env.SUPABASE_SERVICE_ROLE_KEY

    if (!supabaseServiceKey) {
        return NextResponse.json({ success: false, error: 'SERVICE_ROLE_KEY is missing' }, { status: 500 })
    }

    const supabaseAdmin = createClient(supabaseUrl, supabaseServiceKey, {
        auth: { autoRefreshToken: false, persistSession: false }
    })

    try {
        const url = new URL(req.url)
        const limit = Number(url.searchParams.get('limit')) || 50
        const page = Number(url.searchParams.get('page')) || 1
        const offset = (page - 1) * limit

        const { data, error, count } = await supabaseAdmin
            .from('referral_commissions')
            .select('*, beneficiary:profiles!referral_commissions_beneficiary_id_fkey(email), source:profiles!referral_commissions_source_user_id_fkey(email)', { count: 'exact' })
            .order('created_at', { ascending: false })
            .range(offset, offset + limit - 1)

        if (error) {
            console.error('[Settlements API] Fetch error:', error)
            return NextResponse.json({ success: false, error: error.message }, { status: 500 })
        }

        return NextResponse.json({ success: true, data, count, page, limit })

    } catch (error: any) {
        console.error('[Settlements API] Unexpected error:', error)
        return NextResponse.json({ success: false, error: error.message || String(error) }, { status: 500 })
    }
}
