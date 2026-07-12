
import { NextResponse } from 'next/server'
import { supabaseAdmin } from '@/lib/supabaseAdmin'

export async function GET(req: Request) {
    const { searchParams } = new URL(req.url)
    const userId = searchParams.get('userId')

    if (!userId) {
        return NextResponse.json({ error: 'Missing userId' }, { status: 400 })
    }

    try {
        const { data, error } = await supabaseAdmin
            .from('publishing_requests')
            .select('*')
            .eq('user_id', userId)
            .order('created_at', { ascending: false })

        if (error) throw error
        return NextResponse.json({ requests: data })
    } catch (error: any) {
        return NextResponse.json({ error: error.message }, { status: 500 })
    }
}

export async function PATCH(req: Request) {
    try {
        const { userId, requestId, status } = await req.json()

        if (!userId || !requestId || !status) {
            return NextResponse.json({ error: 'Missing required fields' }, { status: 400 })
        }

        // Security check: ensure the request belongs to the user
        const { data: request, error: fetchError } = await supabaseAdmin
            .from('publishing_requests')
            .select('user_id')
            .eq('id', requestId)
            .single()

        if (fetchError || !request || request.user_id !== userId) {
            return NextResponse.json({ error: 'Unauthorized or not found' }, { status: 403 })
        }

        const { data, error } = await supabaseAdmin
            .from('publishing_requests')
            .update({ status })
            .eq('id', requestId)
            .select()

        if (error) throw error
        return NextResponse.json({ success: true, request: data[0] })
    } catch (error: any) {
        return NextResponse.json({ error: error.message }, { status: 500 })
    }
}

export async function POST(req: Request) {
    try {
        const { userId, videoUrl, metadata } = await req.json()

        if (!userId || !videoUrl) {
            return NextResponse.json({ error: 'Missing userId or videoUrl' }, { status: 400 })
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
