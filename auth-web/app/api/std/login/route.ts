import { NextResponse } from 'next/server'
import { supabaseAdmin } from '@/lib/supabaseAdmin'
import { fetchDesktopProfileSnapshot, signDesktopSessionToken } from '@/lib/desktopSession'

export const dynamic = 'force-dynamic'

export async function POST(req: Request) {
    try {
        const { email, password, lang } = await req.json()

        if (!email || !password) {
            return NextResponse.json({ success: false, error: '이메일과 비밀번호를 입력해주세요.' }, { status: 400 })
        }
        const normalizedEmail = String(email).trim().toLowerCase()

        // profiles 테이블에서 pin_code 및 계정 정보 조회
        const { data: profile, error } = await supabaseAdmin
            .from('profiles')
            .select('*')
            .eq('email', normalizedEmail)
            .maybeSingle()

        if (error) {
            console.error('[StdLogin] Profile fetch error:', error.message)
            return NextResponse.json({ success: false, error: '로그인 서버 오류' }, { status: 500 })
        }
        if (!profile) {
            return NextResponse.json({ success: false, error: '등록되지 않은 직원 이메일입니다.' }, { status: 404 })
        }

        if (!profile.pin_code) {
            return NextResponse.json({ success: false, error: '비밀번호가 설정되지 않았습니다. 관리자에게 문의하세요.' }, { status: 401 })
        }

        const dbPassword = String(profile.pin_code).trim()
        const inputPassword = String(password).trim()
        if (dbPassword !== inputPassword) {
            return NextResponse.json({ success: false, error: '비밀번호가 일치하지 않습니다.' }, { status: 401 })
        }

        if (profile.is_approved !== true) {
            return NextResponse.json({ success: false, error: '어드민 승인 대기 중이거나 비활성화된 계정입니다.' }, { status: 403 })
        }

        const membership = String(profile.membership_tier || profile.membership || 'std').toLowerCase()
        if (!['std', 'standard'].includes(membership)) {
            return NextResponse.json({ success: false, error: 'STD 작업자 멤버십 계정만 접속할 수 있습니다.' }, { status: 403 })
        }

        const sessionToken = signDesktopSessionToken(normalizedEmail)

        return NextResponse.json({
            success: true,
            session_token: sessionToken,
            user: {
                id: profile.id,
                email: profile.email,
                full_name: profile.full_name,
                membership: profile.membership || 'std',
            },
        })
    } catch (error: any) {
        return NextResponse.json({ success: false, error: error.message || '로그인 오류' }, { status: 500 })
    }
}
