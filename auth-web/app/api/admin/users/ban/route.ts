
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
        const { userId, ban } = await req.json()

        if (userId === undefined || ban === undefined) {
            return NextResponse.json({ error: 'Missing userId or ban status' }, { status: 400 })
        }

        // app_metadata에 banned 상태를 저장하여 프론트 및 미들웨어에서 체크할 수 있게 함
        const { data, error } = await supabaseAdmin.auth.admin.updateUserById(
            userId,
            { app_metadata: { banned: ban } }
        )

        if (error) throw error

        return NextResponse.json({ success: true, user: data.user })
    } catch (error: any) {
        return NextResponse.json({ error: error.message }, { status: 500 })
    }
}
