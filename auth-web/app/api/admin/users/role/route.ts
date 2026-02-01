
import { createClient } from '@supabase/supabase-js'
import { NextResponse } from 'next/server'

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
        const { userId, role } = await req.json()

        if (!userId || !role) {
            return NextResponse.json({ error: 'Missing userId or role' }, { status: 400 })
        }

        const { data, error } = await supabaseAdmin.auth.admin.updateUserById(
            userId,
            { app_metadata: { membership: role } }
        )

        if (error) throw error

        return NextResponse.json({ success: true, user: data.user })
    } catch (error: any) {
        return NextResponse.json({ error: error.message }, { status: 500 })
    }
}
