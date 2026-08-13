import { NextResponse } from 'next/server'
import { supabaseAdmin } from '@/lib/supabaseAdmin'
import { verifyApprovedDesktopSession } from '@/lib/desktopSession'

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

        if (!(await verifyApprovedDesktopSession(normalizedEmail, String(session_token)))) {
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

        const normalizedFullName = String(full_name || '').trim()
        const normalizedNationality = String(nationality || '').trim()
        const normalizedContact = String(contact || '').trim()

        const { data: updatedRows, error: updateError } = await supabaseAdmin
            .from('profiles')
            .update({
                full_name: normalizedFullName,
                nationality: normalizedNationality,
                contact: normalizedContact,
                preferred_category_ids: resolvedIds,
                preferred_category_names: resolvedNames,
            })
            .eq('email', normalizedEmail)
            .select('id')

        if (updateError) {
            console.error('[DesktopProfileUpdate] Update error:', updateError.message)
            return NextResponse.json({ success: false, error: '프로필 저장에 실패했습니다.' }, { status: 500 })
        }

        // Preferred categories directly affect topic recommendation scoring.
        // Drop unclaimed cached recommendations so the next app refresh scores
        // against the newly saved profile instead of a stale snapshot.
        const { error: cacheClearError } = await supabaseAdmin
            .from('user_topic_recommendations')
            .delete()
            .eq('employee_email', normalizedEmail)
            .eq('is_claimed', false)
        if (cacheClearError) {
            console.warn('[DesktopProfileUpdate] recommendation cache clear warning:', cacheClearError.message)
        }

        // [AIR-0225B Phase 1 follow-up] The admin dashboard
        // (app/api/admin/users/route.ts) reads full_name/contact/nationality
        // from auth.users.user_metadata FIRST, falling back to the profiles
        // row - most existing accounts have these set in user_metadata from
        // signup, not in profiles. Without this, saving here only updates
        // profiles, so the desktop app's own next fetch would show the new
        // value but the admin dashboard would keep showing the old
        // user_metadata value - exactly the "웹어드민에는 여전히 원래 정보가
        // 뜨고" symptom reported after the read-side fix (see
        // fetchDesktopProfileSnapshot in lib/desktopSession.ts).
        const profileId = updatedRows?.[0]?.id
        if (profileId) {
            try {
                const { error: metaError } = await supabaseAdmin.auth.admin.updateUserById(profileId, {
                    user_metadata: {
                        full_name: normalizedFullName,
                        nationality: normalizedNationality,
                        contact: normalizedContact,
                    },
                })
                if (metaError) {
                    console.warn('[DesktopProfileUpdate] user_metadata update warning:', metaError.message)
                }
            } catch (metaErr: any) {
                console.warn('[DesktopProfileUpdate] user_metadata update error:', metaErr?.message)
            }
        }

        return NextResponse.json({ success: true, message: '저장되었습니다.' })
    } catch (error: any) {
        console.error('[DesktopProfileUpdate] Error:', error?.message)
        return NextResponse.json({ success: false, error: '동기화 서버 오류' }, { status: 500 })
    }
}
