
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
        const { userId, full_name, nationality, contact } = await req.json()

        if (!userId) {
            return NextResponse.json({ error: 'Missing userId' }, { status: 400 })
        }

        // 기존 user_metadata 조회 후 병합 (youtube_channel, referrer 등 기존 필드 보존)
        const { data: { user: existingUser }, error: fetchError } = await supabaseAdmin.auth.admin.getUserById(userId)
        if (fetchError) {
            console.error('User fetch error:', fetchError)
            return NextResponse.json({ error: fetchError.message }, { status: 500 })
        }

        // 빈 문자열은 무시 — 기존 값을 덮어쓰지 않음
        const mergedMeta = {
            ...(existingUser?.user_metadata || {}),
            ...(full_name  ? { full_name }  : {}),
            ...(nationality ? { nationality } : {}),
            ...(contact    ? { contact }    : {}),
        }

        const { error } = await supabaseAdmin.auth.admin.updateUserById(userId, {
            user_metadata: mergedMeta
        })

        if (error) {
            console.error('Metadata update error:', error)
            return NextResponse.json({ error: error.message }, { status: 500 })
        }

        return NextResponse.json({ success: true })
    } catch (error: any) {
        return NextResponse.json({ error: error.message }, { status: 500 })
    }
}
