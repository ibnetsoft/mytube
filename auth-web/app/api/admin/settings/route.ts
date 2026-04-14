import { createClient } from '@supabase/supabase-js'
import { NextResponse } from 'next/server'

const getAdmin = () => createClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.SUPABASE_SERVICE_ROLE_KEY!
)

// GET: 현재 저장된 키 로드
export async function GET(req: Request) {
    try {
        const { searchParams } = new URL(req.url)
        const userId = searchParams.get('userId')
        if (!userId) return NextResponse.json({ error: 'Missing userId' }, { status: 400 })

        const { data: { user }, error } = await getAdmin().auth.admin.getUserById(userId)
        if (error || !user) return NextResponse.json({ error: 'User not found' }, { status: 404 })

        const meta = user.user_metadata || {}
        return NextResponse.json({
            gemini:      meta.gemini_api_key     ? '••••' : '',
            youtube:     meta.youtube_api_key    ? '••••' : '',
            elevenlabs:  meta.elevenlabs_api_key ? '••••' : '',
            topview:     meta.topview_api_key    ? '••••' : '',
            topview_uid: meta.topview_uid        ? '••••' : '',
            // 실제 값도 함께 반환 (입력란 pre-fill용)
            gemini_val:      meta.gemini_api_key      || '',
            youtube_val:     meta.youtube_api_key     || '',
            elevenlabs_val:  meta.elevenlabs_api_key  || '',
            topview_val:     meta.topview_api_key     || '',
            topview_uid_val: meta.topview_uid         || '',
        })
    } catch (error: any) {
        return NextResponse.json({ error: error.message }, { status: 500 })
    }
}

// POST: 키 저장 (userId를 body로 받아서 해당 유저의 user_metadata에 저장)
export async function POST(req: Request) {
    try {
        const body = await req.json()
        const { userId, gemini, youtube, elevenlabs, topview, topview_uid } = body

        if (!userId) return NextResponse.json({ error: 'Missing userId' }, { status: 400 })

        const metaUpdate: Record<string, string> = {}
        if (gemini !== undefined)      metaUpdate.gemini_api_key     = gemini
        if (youtube !== undefined)     metaUpdate.youtube_api_key    = youtube
        if (elevenlabs !== undefined)  metaUpdate.elevenlabs_api_key = elevenlabs
        if (topview !== undefined)     metaUpdate.topview_api_key    = topview
        if (topview_uid !== undefined) metaUpdate.topview_uid        = topview_uid

        const { error } = await getAdmin().auth.admin.updateUserById(userId, {
            user_metadata: metaUpdate
        })

        if (error) throw error

        return NextResponse.json({ success: true })
    } catch (error: any) {
        console.error('Settings save failed:', error)
        return NextResponse.json({ error: error.message }, { status: 500 })
    }
}
