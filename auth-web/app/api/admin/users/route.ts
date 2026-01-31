
import { createClient } from '@supabase/supabase-js'
import { NextResponse } from 'next/server'

export const dynamic = 'force-dynamic'

export async function GET() {
    // 환경변수에서 Service Role Key를 가져옴
    // 주의: 클라이언트용 ANON_KEY가 아니라, 관리자용 SERVICE_ROLE_KEY가 필요합니다.
    // .env.local에 SUPABASE_SERVICE_ROLE_KEY를 추가해야 작동합니다.
    const supabaseUrl = process.env.NEXT_PUBLIC_SUPABASE_URL!
    const supabaseServiceKey = process.env.SUPABASE_SERVICE_ROLE_KEY || process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!

    // Service Role Key가 없으면 보안상 경고 (ANON_KEY로는 listUsers 불가)
    if (!process.env.SUPABASE_SERVICE_ROLE_KEY) {
        console.warn("⚠️ API Warning: SUPABASE_SERVICE_ROLE_KEY is missing. User listing might fail.")
    }

    const supabaseAdmin = createClient(supabaseUrl, supabaseServiceKey, {
        auth: {
            autoRefreshToken: false,
            persistSession: false
        }
    })

    try {
        const { data: { users }, error } = await supabaseAdmin.auth.admin.listUsers()

        if (error) throw error

        return NextResponse.json({ users })
    } catch (error: any) {
        return NextResponse.json({ error: error.message }, { status: 500 })
    }
}
