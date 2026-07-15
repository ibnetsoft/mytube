import { createClient } from '@supabase/supabase-js'
import { NextResponse } from 'next/server'
import { isAuthResponse, requireAdmin } from '../../_auth'

export const dynamic = 'force-dynamic'

const getAdmin = () => createClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.SUPABASE_SERVICE_ROLE_KEY!,
    { auth: { persistSession: false } }
)

// GET: list submissions with optional status/provider filters, plus the
// submitter's email (profiles join) for display.
export async function GET(req: Request) {
    try {
        const requester = await requireAdmin(req)
        if (isAuthResponse(requester)) return requester

        const { searchParams } = new URL(req.url)
        const status = searchParams.get('status')
        const provider = searchParams.get('provider')
        const limit = Math.min(Math.max(Number(searchParams.get('limit')) || 50, 1), 200)

        const supabase = getAdmin()
        let query = supabase
            .from('subscription_verifications')
            .select('*, profiles!subscription_verifications_user_id_fkey(email)')
            .order('created_at', { ascending: false })
            .limit(limit)

        if (status) query = query.eq('status', status)
        if (provider) query = query.eq('provider', provider)

        const { data, error } = await query
        if (error) throw error

        return NextResponse.json({ status: 'ok', rows: data || [] })
    } catch (error: any) {
        console.error('[AdminSubscriptionVerifications] GET Error:', error?.message)
        return NextResponse.json({ error: error.message }, { status: 500 })
    }
}
