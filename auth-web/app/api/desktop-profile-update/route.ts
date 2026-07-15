import { NextResponse } from 'next/server'
import { supabaseAdmin } from '@/lib/supabaseAdmin'
import { verifyDesktopSessionToken } from '@/lib/desktopSession'

export const dynamic = 'force-dynamic'

// [AIR-0225B Phase 1] Desktop app's settings-page "프로필 저장" (name/nationality/
// contact/preferred categories), moved off SUPABASE_SERVICE_ROLE_KEY the same
// way desktop-resync moved profile *reads* off it - see lib/desktopSession.ts
// and worknote/AIR-0225B-stage0-service-role-removal-investigation.md.
// Authenticated by session_token (not password), since this runs from the
// already-logged-in settings page.
export async function POST(req: Request) {
    try {
        const { email, session_token, full_name, nationality, contact, preferred_category_ids } = await req.json()

        if (!email || !session_token) {
            return NextResponse.json({ success: false, error: 'Missing email or session_token' }, { status: 400 })
        }
        const normalizedEmail = String(email)

        if (!verifyDesktopSessionToken(normalizedEmail, String(session_token))) {
            return NextResponse.json({ success: false, error: '세션이 만료되었거나 유효하지 않습니다. 다시 로그인해주세요.' }, { status: 401 })
        }

        const requestedIds = Array.isArray(preferred_category_ids)
            ? preferred_category_ids.map((v: any) => String(v).trim()).filter(Boolean)
            : []

        let resolvedIds: (string | number)[] = []
        let resolvedNames: string[] = []
        if (requestedIds.length > 0) {
            const { data: categories, error: catError } = await supabaseAdmin
                .from('categories')
                .select('id, name')
                .in('id', requestedIds)
            if (catError) {
                console.error('[DesktopProfileUpdate] Category fetch error:', catError.message)
                return NextResponse.json({ success: false, error: '카테고리 조회에 실패했습니다.' }, { status: 500 })
            }
            for (const row of categories || []) {
                resolvedIds.push(row.id)
                if (row.name) resolvedNames.push(String(row.name))
            }
        }

        const { error: updateError } = await supabaseAdmin
            .from('profiles')
            .update({
                full_name: String(full_name || '').trim(),
                nationality: String(nationality || '').trim(),
                contact: String(contact || '').trim(),
                preferred_category_ids: resolvedIds,
                preferred_category_names: resolvedNames,
            })
            .eq('email', normalizedEmail)

        if (updateError) {
            console.error('[DesktopProfileUpdate] Update error:', updateError.message)
            return NextResponse.json({ success: false, error: '프로필 저장에 실패했습니다.' }, { status: 500 })
        }

        return NextResponse.json({ success: true, message: '저장되었습니다.' })
    } catch (error: any) {
        console.error('[DesktopProfileUpdate] Error:', error?.message)
        return NextResponse.json({ success: false, error: '동기화 서버 오류' }, { status: 500 })
    }
}
