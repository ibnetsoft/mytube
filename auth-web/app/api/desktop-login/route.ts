import { createClient } from '@supabase/supabase-js'
import { NextResponse } from 'next/server'

export const dynamic = 'force-dynamic'

// 데스크톱 앱(AIR Studio)의 로그인 검증을 서버에서 대신 수행한다.
// SUPABASE_SERVICE_ROLE_KEY는 이 서버 프로세스 밖으로 절대 나가지 않으며,
// 데스크톱 앱은 email/password만 보내고 검증 결과만 돌려받는다.
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
        const { email, password } = await req.json()

        if (!email || !password) {
            return NextResponse.json({ success: false, error: 'Missing email or password' }, { status: 400 })
        }

        // NOTE: profiles has no 'password' column, only 'pin_code' (confirmed
        // against the live schema) - matches the desktop app's original
        // fallback logic which always ended up on pin_code in practice.
        const { data: profile, error } = await supabaseAdmin
            .from('profiles')
            .select('is_approved, pin_code, preferred_language')
            .eq('email', String(email))
            .maybeSingle()

        if (error) {
            console.error('[DesktopLogin] Profile fetch error:', error.message)
            return NextResponse.json({ success: false, error: '로그인 서버 오류' }, { status: 500 })
        }

        if (!profile) {
            return NextResponse.json({ success: false, error: '등록되지 않은 직원 이메일입니다.' }, { status: 404 })
        }

        const isApproved = profile.is_approved
        if (isApproved === false || isApproved === null || isApproved === undefined || ['false', '0', 'none'].includes(String(isApproved).toLowerCase())) {
            return NextResponse.json({ success: false, error: '어드민 승인 대기 중이거나 비활성화된 계정입니다.' }, { status: 403 })
        }

        const dbPassword = String(profile.pin_code || '1234').trim()
        const inputPassword = String(password).trim()

        if (dbPassword !== inputPassword) {
            return NextResponse.json({ success: false, error: '비밀번호가 일치하지 않습니다.' }, { status: 401 })
        }

        return NextResponse.json({
            success: true,
            preferred_language: profile.preferred_language || '',
        })
    } catch (error: any) {
        return NextResponse.json({ success: false, error: error.message }, { status: 500 })
    }
}
