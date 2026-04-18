import { createClient } from '@supabase/supabase-js'
import { NextResponse } from 'next/server'

export async function GET(_req: Request, { params }: { params: { id: string } }) {
    try {
        const supabaseAdmin = createClient(
            process.env.NEXT_PUBLIC_SUPABASE_URL!,
            process.env.SUPABASE_SERVICE_ROLE_KEY!
        )

        const { data: { user }, error } = await supabaseAdmin.auth.admin.getUserById(params.id)
        if (error || !user) throw error || new Error('User not found')

        const meta = user.user_metadata || {}
        return NextResponse.json({
            gemini: meta.gemini_api_key || '',
            youtube: meta.youtube_api_key || '',
            elevenlabs: meta.elevenlabs_api_key || '',
            topview: meta.topview_api_key || '',
            topview_uid: meta.topview_uid || '',
            youtube_channel: meta.youtube_channel || '',
            youtube_handle: meta.youtube_handle || '',
        })
    } catch (error: any) {
        return NextResponse.json({ error: error.message }, { status: 500 })
    }
}

export async function POST(req: Request, { params }: { params: { id: string } }) {
    try {
        const body = await req.json()
        const userId = params.id
        const { gemini, youtube, elevenlabs, topview, topview_uid, youtube_channel, youtube_handle } = body

        const supabaseAdmin = createClient(
            process.env.NEXT_PUBLIC_SUPABASE_URL!,
            process.env.SUPABASE_SERVICE_ROLE_KEY!
        )

        // 기존 user_metadata 조회 후 병합 (full_name, nationality, contact 등 보존)
        const { data: { user: existingUser } } = await supabaseAdmin.auth.admin.getUserById(userId)
        const merged = { ...(existingUser?.user_metadata || {}) }
        if (gemini !== undefined)      merged.gemini_api_key = gemini
        if (youtube !== undefined)     merged.youtube_api_key = youtube
        if (elevenlabs !== undefined)  merged.elevenlabs_api_key = elevenlabs
        if (topview !== undefined)     merged.topview_api_key = topview
        if (topview_uid !== undefined) merged.topview_uid = topview_uid
        if (youtube_channel !== undefined) merged.youtube_channel = youtube_channel
        if (youtube_handle !== undefined)  merged.youtube_handle = youtube_handle

        const { error } = await supabaseAdmin.auth.admin.updateUserById(userId, {
            user_metadata: merged
        })

        if (error) throw error

        return NextResponse.json({ success: true })
    } catch (error: any) {
        console.error('Admin user settings update failed:', error)
        return NextResponse.json({ error: error.message }, { status: 500 })
    }
}
