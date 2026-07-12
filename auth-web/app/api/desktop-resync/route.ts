import { NextResponse } from 'next/server'
import { fetchDesktopProfileSnapshot, verifyDesktopSessionToken } from '@/lib/desktopSession'

export const dynamic = 'force-dynamic'

// [AIR-0225B Batch A] Session resume for the desktop app (app relaunch,
// periodic re-sync) WITHOUT a password. Requires the session_token minted by
// /api/desktop-login - a bare email is never enough, since that would leak
// membership/token_balance/shared API keys to anyone who knows an address.
// See lib/desktopSession.ts for the token scheme.
export async function POST(req: Request) {
    try {
        const { email, session_token } = await req.json()

        if (!email || !session_token) {
            return NextResponse.json({ success: false, error: 'Missing email or session_token' }, { status: 400 })
        }
        const normalizedEmail = String(email)

        if (!verifyDesktopSessionToken(normalizedEmail, String(session_token))) {
            return NextResponse.json({ success: false, error: '세션이 만료되었거나 유효하지 않습니다. 다시 로그인해주세요.' }, { status: 401 })
        }

        const snapshot = await fetchDesktopProfileSnapshot(normalizedEmail)
        if (!snapshot) {
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
        })
    } catch (error: any) {
        console.error('[DesktopResync] Error:', error?.message)
        return NextResponse.json({ success: false, error: '동기화 서버 오류' }, { status: 500 })
    }
}
