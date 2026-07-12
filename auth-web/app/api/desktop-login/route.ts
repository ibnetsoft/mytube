import { NextResponse } from 'next/server'
import { supabaseAdmin } from '@/lib/supabaseAdmin'
import { fetchDesktopProfileSnapshot, signDesktopSessionToken } from '@/lib/desktopSession'

export const dynamic = 'force-dynamic'

// 데스크톱 앱(AIR Studio)의 로그인 검증을 서버에서 대신 수행한다.
// SUPABASE_SERVICE_ROLE_KEY는 이 서버 프로세스 밖으로 절대 나가지 않으며,
// 데스크톱 앱은 email/password만 보내고 검증 결과만 돌려받는다.
export async function POST(req: Request) {
    try {
        const { email, password, lang } = await req.json()

        if (!email || !password) {
            return NextResponse.json({ success: false, error: 'Missing email or password' }, { status: 400 })
        }
        const normalizedEmail = String(email)

        // NOTE: profiles has no 'password' column, only 'pin_code' (confirmed
        // against the live schema) - matches the desktop app's original
        // fallback logic which always ended up on pin_code in practice.
        const { data: pinRow, error } = await supabaseAdmin
            .from('profiles')
            .select('pin_code')
            .eq('email', normalizedEmail)
            .maybeSingle()

        if (error) {
            console.error('[DesktopLogin] Profile fetch error:', error.message)
            return NextResponse.json({ success: false, error: '로그인 서버 오류' }, { status: 500 })
        }
        if (!pinRow) {
            return NextResponse.json({ success: false, error: '등록되지 않은 직원 이메일입니다.' }, { status: 404 })
        }

        const dbPassword = String(pinRow.pin_code || '1234').trim()
        const inputPassword = String(password).trim()
        if (dbPassword !== inputPassword) {
            return NextResponse.json({ success: false, error: '비밀번호가 일치하지 않습니다.' }, { status: 401 })
        }

        // [AIR-0225B Batch A] membership/token_balance/global_settings + the
        // language-save-in-same-request are all handled by the shared helper so
        // /api/desktop-resync (no-password session resume) returns an identical
        // shape from the same source of truth.
        const snapshot = await fetchDesktopProfileSnapshot(normalizedEmail, lang ? String(lang) : undefined)
        if (!snapshot) {
            // Profile disappeared between the pin_code check above and here -
            // vanishingly unlikely, but fail closed rather than 500.
            return NextResponse.json({ success: false, error: '등록되지 않은 직원 이메일입니다.' }, { status: 404 })
        }
        if (!snapshot.isApproved) {
            return NextResponse.json({ success: false, error: '어드민 승인 대기 중이거나 비활성화된 계정입니다.' }, { status: 403 })
        }

        return NextResponse.json({
            success: true,
            preferred_language: snapshot.profile.preferred_language,
            membership: snapshot.profile.membership,
            token_balance: snapshot.profile.token_balance,
            global_settings: snapshot.profile.global_settings,
            // [AIR-0225B Batch A] Opaque, HMAC-signed - lets the desktop app
            // resume a session later (app relaunch, cookie-restored login)
            // without resending the password or the local backend needing
            // SUPABASE_SERVICE_ROLE_KEY. See lib/desktopSession.ts.
            session_token: signDesktopSessionToken(normalizedEmail),
        })
    } catch (error: any) {
        return NextResponse.json({ success: false, error: error.message }, { status: 500 })
    }
}
