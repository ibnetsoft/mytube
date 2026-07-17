
import { NextResponse } from 'next/server'
import { supabaseAdmin } from '@/lib/supabaseAdmin'
import { verifyDesktopSessionToken } from '@/lib/desktopSession'

export const dynamic = 'force-dynamic'

// [AIR-0225B] 예전에는 body의 userId(UUID)만 믿고 auth.users 메타데이터를
// 덮어썼다 - UUID만 알면 타인의 프로필(full_name/nationality/contact)을
// 조작할 수 있는 구멍이었다. 이제 email + HMAC session_token 을 검증하고
// (desktop-referrals와 동일 스킴), user_id 는 세션 email 로부터 서버가
// 직접 해석한다(클라이언트 제공 userId 는 신뢰하지 않음).
async function resolveUserId(email: string): Promise<string | null> {
    const { data, error } = await supabaseAdmin
        .from('profiles')
        .select('id')
        .eq('email', email)
        .maybeSingle()
    if (error || !data) return null
    return data.id
}

export async function POST(req: Request) {
    try {
        const { email, session_token, full_name, nationality, contact } = await req.json()

        if (!email || !session_token) {
            return NextResponse.json({ error: 'missing_email_or_session_token' }, { status: 401 })
        }
        if (!verifyDesktopSessionToken(String(email), String(session_token))) {
            return NextResponse.json({ error: 'invalid_or_expired_session' }, { status: 401 })
        }

        const userId = await resolveUserId(String(email))
        if (!userId) {
            return NextResponse.json({ error: 'Invalid user' }, { status: 401 })
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
