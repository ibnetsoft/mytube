import { createClient } from '@supabase/supabase-js'
import { NextResponse } from 'next/server'
import { isAuthResponse, requireSuperAdmin } from '../../../_auth'

export async function POST(req: Request) {
    const requester = await requireSuperAdmin(req)
    if (isAuthResponse(requester)) return requester

    try {
        const body = await req.json()
        const { commission_id } = body

        if (!commission_id) {
            return NextResponse.json({ success: false, error: 'commission_id is required' }, { status: 400 })
        }

        const supabaseUrl = process.env.NEXT_PUBLIC_SUPABASE_URL!
        const supabaseServiceKey = process.env.SUPABASE_SERVICE_ROLE_KEY

        if (!supabaseServiceKey) {
            return NextResponse.json({ success: false, error: 'SERVICE_ROLE_KEY is missing' }, { status: 500 })
        }

        const supabaseAdmin = createClient(supabaseUrl, supabaseServiceKey, {
            auth: { autoRefreshToken: false, persistSession: false }
        })

        // Call the RPC to process the payout atomically
        const { data, error } = await supabaseAdmin.rpc('process_referral_payout', {
            p_commission_id: commission_id
        })

        if (error) {
            console.error('[Payout API] RPC execution error:', error)
            return NextResponse.json({ success: false, error: error.message }, { status: 500 })
        }

        if (data && data.success === false) {
            return NextResponse.json({ success: false, error: data.error }, { status: 400 })
        }

        return NextResponse.json({ success: true, data })

    } catch (error: any) {
        console.error('[Payout API] Unexpected error:', error)
        return NextResponse.json({ success: false, error: error.message || String(error) }, { status: 500 })
    }
}
