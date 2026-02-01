
import { createClient } from '@supabase/supabase-js'
import { NextResponse } from 'next/server'

export const dynamic = 'force-dynamic'

export async function POST(req: Request) {
    const supabaseUrl = process.env.NEXT_PUBLIC_SUPABASE_URL!
    const supabaseServiceKey = process.env.SUPABASE_SERVICE_ROLE_KEY || process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!

    const supabaseAdmin = createClient(supabaseUrl, supabaseServiceKey, {
        auth: {
            autoRefreshToken: false,
            persistSession: false
        }
    })

    try {
        const { userId } = await req.json()

        if (!userId) {
            return NextResponse.json({ error: 'Missing userId' }, { status: 400 })
        }

        // Get user app_metadata
        const { data: { user }, error } = await supabaseAdmin.auth.admin.getUserById(userId)

        if (error || !user) {
            return NextResponse.json({ error: 'Invalid license key' }, { status: 401 })
        }

        return NextResponse.json({
            success: true,
            membership: user.app_metadata?.membership || 'standard',
            email: user.email
        })
    } catch (error: any) {
        return NextResponse.json({ error: error.message }, { status: 500 })
    }
}
