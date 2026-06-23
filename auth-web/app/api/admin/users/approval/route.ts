import { createClient } from '@supabase/supabase-js'
import { NextResponse } from 'next/server'
import { isAuthResponse, requireAdmin } from '../../_auth'

export const dynamic = 'force-dynamic'

export async function POST(req: Request) {
    const requester = await requireAdmin(req)
    if (isAuthResponse(requester)) return requester

    const supabaseUrl = process.env.NEXT_PUBLIC_SUPABASE_URL!
    const supabaseServiceKey = process.env.SUPABASE_SERVICE_ROLE_KEY

    if (!supabaseServiceKey) {
        return NextResponse.json({ error: 'Server configuration error' }, { status: 500 })
    }

    try {
        const { userId, approved } = await req.json()
        if (!userId || approved === undefined) {
            return NextResponse.json({ error: 'Missing userId or approved status' }, { status: 400 })
        }

        const supabaseAdmin = createClient(supabaseUrl, supabaseServiceKey, {
            auth: { persistSession: false }
        })

        const isApproved = Boolean(approved)
        const { error: profileError } = await supabaseAdmin
            .from('profiles')
            .update({
                is_approved: isApproved,
                signup_status: isApproved ? 'approved' : 'pending'
            })
            .eq('id', userId)

        if (profileError) throw profileError

        return NextResponse.json({ success: true })
    } catch (error: any) {
        return NextResponse.json({ error: error.message }, { status: 500 })
    }
}
