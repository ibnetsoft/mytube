import { createClient } from '@supabase/supabase-js'
import { NextResponse } from 'next/server'

export const dynamic = 'force-dynamic'

const getAdmin = () => createClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.SUPABASE_SERVICE_ROLE_KEY!
)

function normalizeQueueItem(row: any) {
    const metadata = row?.metadata || {}
    const title = metadata.playlist_title || metadata.title || row?.project_name || 'Untitled'
    const appMode = metadata.app_mode || metadata.display_type || 'longform'
    const renderStyle = metadata.render_style || null
    const queueType = metadata.queue_type || null
    const trackDurations = Array.isArray(metadata.track_durations) ? metadata.track_durations : []
    const totalDurationSeconds =
        Number(metadata.total_duration_seconds || 0) ||
        trackDurations.reduce((sum: number, item: any) => sum + (Number(item || 0) || 0), 0) ||
        null
    const trackCount =
        Number(metadata.track_count || 0) ||
        (trackDurations.length ? trackDurations.length : null)
    const isMusicQueue =
        appMode === 'longform_music' ||
        renderStyle === 'music_playlist' ||
        queueType === 'music_playlist_final'

    return {
        ...row,
        metadata: {
            ...metadata,
            title,
            app_mode: appMode,
            render_style: renderStyle,
            queue_type: queueType,
            is_music_queue: isMusicQueue,
            admin_publish_ready: metadata.admin_publish_ready ?? null,
            admin_publish_status: metadata.admin_publish_status ?? null,
            admin_action_required: metadata.admin_action_required ?? null,
            upload_owner: metadata.upload_owner ?? null,
            publish_owner: metadata.publish_owner ?? null,
            worker_platform: metadata.worker_platform ?? null,
            track_count: trackCount,
            track_durations: trackDurations,
            total_duration_seconds: totalDurationSeconds,
        },
    }
}

export async function GET() {
    try {
        const sb = getAdmin()
        const { data, error } = await sb
            .from('remote_render_queue')
            .select('*')
            .order('created_at', { ascending: false })
            .limit(100)

        if (error) throw error
        return NextResponse.json({ success: true, queue: (data || []).map(normalizeQueueItem) })
    } catch (e: any) {
        return NextResponse.json({ error: e.message }, { status: 500 })
    }
}

export async function DELETE(req: Request) {
    try {
        const { searchParams } = new URL(req.url)
        const id = searchParams.get('id')
        if (!id) return NextResponse.json({ error: 'Missing id' }, { status: 400 })

        const sb = getAdmin()
        const { error } = await sb
            .from('remote_render_queue')
            .delete()
            .eq('id', id)

        if (error) throw error
        return NextResponse.json({ success: true })
    } catch (e: any) {
        return NextResponse.json({ error: e.message }, { status: 500 })
    }
}
