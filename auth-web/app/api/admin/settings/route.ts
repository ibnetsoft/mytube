import { createClient } from '@supabase/supabase-js'
import { NextResponse } from 'next/server'
import { requireSuperAdmin, isAuthResponse } from '../_auth'

const getAdmin = () => createClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.SUPABASE_SERVICE_ROLE_KEY!
)

// GET: 현재 저장된 키 로드
// [AIR-0227D-VALIDATION additional static check 3 - security hotfix, SEVERE]
// had no admin auth check at all - returned another user's real API key
// VALUES in plaintext (gemini_val/youtube_val/elevenlabs_val/topview_val)
// for any userId supplied as a query param, no login required. Matches the
// already-secured sibling admin/users/api-keys/route.ts (same concern,
// already requireSuperAdmin-gated) - this route appears to be an
// older/duplicate path that was left behind unsecured.
export async function GET(req: Request) {
    const requester = await requireSuperAdmin(req)
    if (isAuthResponse(requester)) return requester

    try {
        const { searchParams } = new URL(req.url)
        const userId = searchParams.get('userId')
        if (!userId) return NextResponse.json({ error: 'Missing userId' }, { status: 400 })

        const { data: { user }, error } = await getAdmin().auth.admin.getUserById(userId)
        if (error || !user) return NextResponse.json({ error: 'User not found' }, { status: 404 })

        // [AIR-0227D-SECURITY-HOTFIX Stage 6] the *_val fields used to
        // return the real key values ("입력란 pre-fill용" per the old
        // comment) - removed. Per policy, API keys are never returned in
        // plaintext to the browser, even to an authenticated super admin;
        // an admin overwrites a key without being able to read the
        // existing one first.
        const meta = user.user_metadata || {}
        return NextResponse.json({
            gemini:      meta.gemini_api_key     ? '••••' : '',
            youtube:     meta.youtube_api_key    ? '••••' : '',
            elevenlabs:  meta.elevenlabs_api_key ? '••••' : '',
            topview:     meta.topview_api_key    ? '••••' : '',
            topview_uid: meta.topview_uid        ? '••••' : '',
        })
    } catch (error: any) {
        return NextResponse.json({ error: error.message }, { status: 500 })
    }
}

// POST: 키 저장 (userId를 body로 받아서 해당 유저의 user_metadata에 저장)
export async function POST(req: Request) {
    const requester = await requireSuperAdmin(req)
    if (isAuthResponse(requester)) return requester

    try {
        const body = await req.json()
        const { userId, gemini, youtube, elevenlabs, topview, topview_uid } = body

        if (!userId) return NextResponse.json({ error: 'Missing userId' }, { status: 400 })

        // 기존 user_metadata 조회 후 병합 (full_name, nationality, contact 등 보존)
        const { data: { user: existingUser } } = await getAdmin().auth.admin.getUserById(userId)
        const merged = { ...(existingUser?.user_metadata || {}) }
        if (gemini !== undefined)      merged.gemini_api_key     = gemini
        if (youtube !== undefined)     merged.youtube_api_key    = youtube
        if (elevenlabs !== undefined)  merged.elevenlabs_api_key = elevenlabs
        if (topview !== undefined)     merged.topview_api_key    = topview
        if (topview_uid !== undefined) merged.topview_uid        = topview_uid

        const { error } = await getAdmin().auth.admin.updateUserById(userId, {
            user_metadata: merged
        })

        if (error) throw error

        return NextResponse.json({ success: true })
    } catch (error: any) {
        console.error('Settings save failed:', error)
        return NextResponse.json({ error: error.message }, { status: 500 })
    }
}
