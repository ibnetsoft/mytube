
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
        // 1. Auth 유저 목록 가져오기
        const { data: { users }, error: authError } = await supabaseAdmin.auth.admin.listUsers()
        if (authError) throw authError

        // 2. Public Profiles (토큰 잔액 등) 가져오기
        const { data: profiles, error: profileError } = await supabaseAdmin
            .from('profiles')
            .select('*')
        
        if (profileError) {
            console.error("Profile Fetch Error:", profileError)
        }

        // 3. 데이터 병합 (User + Profile)
        const enrichedUsers = users.map(user => {
            const profile = profiles?.find(p => p.id === user.id) || {}
            return {
                ...user,
                profile: {
                    token_balance: profile.token_balance || 0,
                    membership_tier: profile.membership_tier || 'standard',
                    video_limit: profile.video_limit || 50,
                    current_usage: profile.current_usage || 0
                }
            }
        })

        return NextResponse.json({ users: enrichedUsers })
    } catch (error: any) {
        return NextResponse.json({ error: error.message }, { status: 500 })
    }
}
