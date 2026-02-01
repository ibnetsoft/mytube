
import { createClient } from '@supabase/supabase-js'
import { NextResponse } from 'next/server'

export async function POST(req: Request) {
    const supabaseUrl = process.env.NEXT_PUBLIC_SUPABASE_URL!
    const supabaseServiceKey = process.env.SUPABASE_SERVICE_ROLE_KEY || process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!

    const supabaseAdmin = createClient(supabaseUrl, supabaseServiceKey)

    try {
        const { userId, videoUrl, metadata } = await req.json()

        if (!userId || !videoUrl) {
            return NextResponse.json({ error: 'Missing userId or videoUrl' }, { status: 400 })
        }

        // Verify user exists
        const { data: { user }, error: userError } = await supabaseAdmin.auth.admin.getUserById(userId)
        if (userError || !user) {
            return NextResponse.json({ error: 'Invalid user' }, { status: 401 })
        }

        const { data, error } = await supabaseAdmin
            .from('publishing_requests')
            .insert({
                user_id: userId,
                video_url: videoUrl,
                metadata: metadata || {},
                status: 'pending'
            })
            .select()

        if (error) throw error

        return NextResponse.json({ success: true, request: data[0] })
    } catch (error: any) {
        return NextResponse.json({ error: error.message }, { status: 500 })
    }
}
