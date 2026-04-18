import { createClient } from '@supabase/supabase-js'
import { NextResponse } from 'next/server'

export async function POST(req: Request) {
    const supabaseUrl = process.env.NEXT_PUBLIC_SUPABASE_URL!
    const supabaseServiceKey = process.env.SUPABASE_SERVICE_ROLE_KEY!

    const supabaseAdmin = createClient(supabaseUrl, supabaseServiceKey, {
        auth: { autoRefreshToken: false, persistSession: false }
    })

    try {
        const body = await req.json()
        // DashboardContent.tsx sends { userId, membership }
        const { userId, membership } = body

        if (!userId || !membership) {
            return NextResponse.json({ error: 'Missing userId or membership' }, { status: 400 })
        }

        // 1. 기존 app_metadata 조회 후 membership만 업데이트 (다른 필드 보존)
        const { data: { user: existingUser }, error: fetchError } = await supabaseAdmin.auth.admin.getUserById(userId)
        if (fetchError) throw fetchError
        const mergedMeta = { ...(existingUser?.app_metadata || {}), membership }

        const { data: authData, error: authError } = await supabaseAdmin.auth.admin.updateUserById(
            userId,
            { app_metadata: mergedMeta }
        )
        if (authError) throw authError

        // 2. Profiles 테이블 업데이트 (DB 쿼리/대시보드에서 참조)
        const { error: profileError } = await supabaseAdmin
            .from('profiles')
            .update({ membership: membership })
            .eq('id', userId)

        if (profileError) {
            console.error("Profile update error:", profileError)
        }

        return NextResponse.json({ success: true, user: authData.user })
    } catch (error: any) {
        console.error('Role Update Error:', error)
        return NextResponse.json({ error: error.message }, { status: 500 })
    }
}
