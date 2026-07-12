import { NextResponse } from 'next/server'
import { supabaseAdmin } from '@/lib/supabaseAdmin'

export const dynamic = 'force-dynamic'

// Same password complexity rule enforced at signup (app/routers/auth.py's
// post_auth_register): 8+ chars, upper, lower, digit, special.
const PASSWORD_PATTERN = /^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)(?=.*[!@#$%^&*()_+\-=\[\]{};':"\\|,.<>\/?]).{8,}$/

// 데스크톱 앱(AIR Studio)의 "비밀번호 변경"을 서버에서 대신 수행한다.
// SUPABASE_SERVICE_ROLE_KEY는 이 서버 프로세스 밖으로 절대 나가지 않으며,
// 데스크톱 앱은 email/current_password/new_password만 보내고 결과만 돌려받는다.
// 로그인(desktop-login)과 동일하게 pin_code 컬럼을 실제 비밀번호로 사용한다.
export async function POST(req: Request) {
    try {
        const { email, current_password, new_password } = await req.json()

        if (!email || !current_password || !new_password) {
            return NextResponse.json({ success: false, error: '필수 항목이 누락되었습니다.' }, { status: 400 })
        }

        if (!PASSWORD_PATTERN.test(String(new_password))) {
            return NextResponse.json({ success: false, error: '새 비밀번호가 규칙을 만족하지 않습니다 (8자 이상, 대소문자·숫자·특수문자 포함).' }, { status: 400 })
        }

        const { data: profile, error } = await supabaseAdmin
            .from('profiles')
            .select('id, is_approved, pin_code')
            .eq('email', String(email))
            .maybeSingle()

        if (error) {
            console.error('[DesktopChangePassword] Profile fetch error:', error.message)
            return NextResponse.json({ success: false, error: '서버 오류' }, { status: 500 })
        }

        if (!profile) {
            return NextResponse.json({ success: false, error: '등록되지 않은 계정입니다.' }, { status: 404 })
        }

        const isApproved = profile.is_approved
        if (isApproved === false || isApproved === null || isApproved === undefined || ['false', '0', 'none'].includes(String(isApproved).toLowerCase())) {
            return NextResponse.json({ success: false, error: '어드민 승인 대기 중이거나 비활성화된 계정입니다.' }, { status: 403 })
        }

        const dbPassword = String(profile.pin_code || '1234').trim()
        if (dbPassword !== String(current_password).trim()) {
            return NextResponse.json({ success: false, error: '현재 비밀번호가 일치하지 않습니다.' }, { status: 401 })
        }

        const { error: updateError } = await supabaseAdmin
            .from('profiles')
            .update({ pin_code: String(new_password).trim() })
            .eq('id', profile.id)

        if (updateError) {
            console.error('[DesktopChangePassword] Update error:', updateError.message)
            return NextResponse.json({ success: false, error: '비밀번호 변경에 실패했습니다.' }, { status: 500 })
        }

        return NextResponse.json({ success: true, message: '비밀번호가 변경되었습니다.' })
    } catch (error: any) {
        return NextResponse.json({ success: false, error: error.message }, { status: 500 })
    }
}
