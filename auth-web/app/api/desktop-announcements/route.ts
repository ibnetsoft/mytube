import { NextResponse } from 'next/server'
import { supabaseAdmin } from '@/lib/supabaseAdmin'
import { verifyDesktopSessionToken } from '@/lib/desktopSession'

export const dynamic = 'force-dynamic'

// 웹어드민 -> 전체 유저 공지사항 게시판의 유저 조회 브릿지. 공지는 모든
// 로그인 직원에게 동일한 내용이 나가므로 user_id별 필터는 없지만, 그래도
// 미로그인/미승인 클라이언트가 내부 공지를 볼 수 없도록 desktop-referrals와
// 동일한 email + HMAC session_token 검증을 거친다.
//
// is_published=false(초안)는 절대 이 브릿지로 나가지 않는다 - .eq('is_published', true)
// 필터가 유일한 노출 경로 차단선이다.

export async function POST(req: Request) {
    try {
        const body = await req.json()
        const { email, session_token, action } = body

        if (!email || !session_token || !action) {
            return NextResponse.json({ success: false, error: 'Missing email, session_token or action' }, { status: 400 })
        }
        if (!verifyDesktopSessionToken(String(email), String(session_token))) {
            return NextResponse.json({ success: false, error: '세션이 만료되었거나 유효하지 않습니다. 다시 로그인해주세요.' }, { status: 401 })
        }

        if (String(action) !== 'list') {
            return NextResponse.json({ success: false, error: `Unknown action: ${action}` }, { status: 400 })
        }

        const { data, error } = await supabaseAdmin
            .from('announcements')
            .select('id, title, body, is_pinned, pinned_at, published_at, created_at')
            .eq('is_published', true)
            .order('is_pinned', { ascending: false })
            .order('pinned_at', { ascending: false, nullsFirst: false })
            .order('published_at', { ascending: false, nullsFirst: false })
            .limit(100)

        if (error) {
            return NextResponse.json({ success: false, error: '공지사항 조회에 실패했습니다.' }, { status: 500 })
        }

        return NextResponse.json({ success: true, announcements: data || [] })
    } catch (error: any) {
        console.error('[DesktopAnnouncements] Error:', error?.message)
        return NextResponse.json({ success: false, error: '공지사항 서버 오류' }, { status: 500 })
    }
}
