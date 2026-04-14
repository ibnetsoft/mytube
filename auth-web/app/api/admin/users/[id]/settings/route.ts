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
        })
    } catch (error: any) {
        return NextResponse.json({ error: error.message }, { status: 500 })
    }
}

export async function POST(req: Request, { params }: { params: { id: string } }) {
    try {
        const body = await req.json()
        const userId = params.id
        const { gemini, youtube, elevenlabs, topview, topview_uid } = body

        const supabaseAdmin = createClient(
            process.env.NEXT_PUBLIC_SUPABASE_URL!,
            process.env.SUPABASE_SERVICE_ROLE_KEY!
        )

        const metaUpdate: Record<string, string> = {}
        if (gemini !== undefined)      metaUpdate.gemini_api_key = gemini
        if (youtube !== undefined)     metaUpdate.youtube_api_key = youtube
        if (elevenlabs !== undefined)  metaUpdate.elevenlabs_api_key = elevenlabs
        if (topview !== undefined)     metaUpdate.topview_api_key = topview
        if (topview_uid !== undefined) metaUpdate.topview_uid = topview_uid

        const { error } = await supabaseAdmin.auth.admin.updateUserById(userId, {
            user_metadata: metaUpdate
        })

        if (error) throw error

        return NextResponse.json({ success: true })
    } catch (error: any) {
        console.error('Admin user settings update failed:', error)
        return NextResponse.json({ error: error.message }, { status: 500 })
    }
}
