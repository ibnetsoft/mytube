import { createClient } from '@supabase/supabase-js'
import { NextResponse } from 'next/server'
import { requireSuperAdmin, isAuthResponse } from '../_auth'

export const dynamic = 'force-dynamic'

// [AIR-0227D-VALIDATION Stage 1 - security hotfix] This route had NO admin
// auth check at all until this fix - GET/DELETE went straight to a
// service-role client, meaning anyone who found the URL could list or
// delete production render-queue rows with zero login. requireSuperAdmin
// matches how this feature is gated in the UI (DashboardContent.tsx's
// render-queue tab has `superOnly: true`), and the frontend already sends
// `Authorization: Bearer <supabase session token>` via its `adminFetch`
// helper (components/DashboardContent.tsx:388-392) - this fix only makes
// the server actually check what the client was already sending, so it
// does not change the existing admin UI's behavior.
const getAdmin = () => createClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.SUPABASE_SERVICE_ROLE_KEY!
)

// Minimal structured audit trail (server log only - no dedicated audit
// table exists yet in this codebase, and adding one is out of scope for an
// emergency, standalone security commit). Never logs secrets/tokens.
function auditLog(action: string, requesterEmail: string | undefined, detail: Record<string, unknown>) {
    console.warn(`[admin-audit] action=${action} requester=${requesterEmail || 'unknown'} detail=${JSON.stringify(detail)}`)
}

function buildDriveViewLink(fileId?: string | null) {
    if (!fileId) return null
    return `https://drive.google.com/file/d/${fileId}/view`
}

function normalizeQueueItem(row: any, topicRow?: any) {
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
    const introVideoReady = metadata.intro_video_ready ?? null
    const introBgmReady = metadata.intro_bgm_ready ?? null
    const introVideoPromptReady = metadata.intro_video_prompt_ready ?? null
    const introBgmPromptReady = metadata.intro_bgm_prompt_ready ?? null
    const introMode = metadata.intro_mode ?? null
    const introBgmUsage = metadata.intro_bgm_usage ?? null

    const category = topicRow?.categories || null
    const uploadChannelId = category?.upload_channel_id ?? null
    const uploadChannelName = category?.upload_channel_name || category?.upload_channel_handle || null

    return {
        ...row,
        result_view_link: buildDriveViewLink(row?.result_file_id),
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
            intro_video_ready: introVideoReady,
            intro_bgm_ready: introBgmReady,
            intro_video_prompt_ready: introVideoPromptReady,
            intro_bgm_prompt_ready: introBgmPromptReady,
            intro_mode: introMode,
            intro_bgm_usage: introBgmUsage,
            upload_channel_id: uploadChannelId,
            channel_name: uploadChannelName,
            topic_title: topicRow?.topic || null,
        },
    }
}

export async function GET(req: Request) {
    const requester = await requireSuperAdmin(req)
    if (isAuthResponse(requester)) return requester

    try {
        const sb = getAdmin()
        const { data, error } = await sb
            .from('remote_render_queue')
            .select('*')
            .order('created_at', { ascending: false })
            .limit(100)

        if (error) throw error

        const rows = data || []
        const projectIds = Array.from(new Set(rows.map((r: any) => r.project_id).filter((id: any) => id != null)))

        const topicByProjectId = new Map<string, any>()
        if (projectIds.length > 0) {
            const { data: topicRows } = await sb
                .from('topics_queue')
                .select('local_project_id, topic, categories(upload_channel_id, upload_channel_name, upload_channel_handle)')
                .in('local_project_id', projectIds)

            for (const t of topicRows || []) {
                if (t.local_project_id != null) topicByProjectId.set(String(t.local_project_id), t)
            }
        }

        const queue = rows.map((row: any) => normalizeQueueItem(row, topicByProjectId.get(String(row.project_id))))
        return NextResponse.json({ success: true, queue })
    } catch (e: any) {
        return NextResponse.json({ error: e.message }, { status: 500 })
    }
}

export async function POST(req: Request) {
    const requester = await requireSuperAdmin(req)
    if (isAuthResponse(requester)) return requester

    try {
        const { id } = await req.json()
        if (!id) return NextResponse.json({ error: 'Missing id' }, { status: 400 })

        const sb = getAdmin()
        const { data: task, error: taskError } = await sb
            .from('remote_render_queue')
            .select('*')
            .eq('id', id)
            .single()

        if (taskError) throw taskError
        if (task.status !== 'completed' || !task.result_file_id) {
            return NextResponse.json({ error: '완료된 렌더링 결과물이 없습니다.' }, { status: 400 })
        }
        if (!task.email) {
            return NextResponse.json({ error: '작업에 사용자 이메일 정보가 없습니다.' }, { status: 400 })
        }

        const { data: topicRow } = await sb
            .from('topics_queue')
            .select('topic, categories(upload_channel_id, upload_channel_name, upload_channel_handle)')
            .eq('local_project_id', task.project_id)
            .maybeSingle()

        const category = (topicRow as any)?.categories || null
        const channelId = category?.upload_channel_id ?? null
        if (!channelId) {
            return NextResponse.json({ error: '이 주제의 카테고리에 업로드 채널이 배정되지 않았습니다. 먼저 채널을 배정해주세요.' }, { status: 400 })
        }

        const { data: profile, error: profileError } = await sb
            .from('profiles')
            .select('id')
            .eq('email', task.email)
            .maybeSingle()

        if (profileError) throw profileError
        if (!profile?.id) {
            return NextResponse.json({ error: `사용자를 찾을 수 없습니다: ${task.email}` }, { status: 404 })
        }

        const title = (topicRow as any)?.topic || task.project_name || `Project ${task.project_id}`
        const videoUrl = buildDriveViewLink(task.result_file_id)

        const { data: existingRows } = await sb
            .from('publishing_requests')
            .select('id, metadata')
            .eq('user_id', profile.id)

        const existingRow = (existingRows || []).find(
            (row: any) => String(row?.metadata?.project_id || '') === String(task.project_id)
        )

        const metadataPayload = {
            ...(existingRow?.metadata || {}),
            project_id: task.project_id,
            title,
            drive_video_file_id: task.result_file_id,
            channel_id: channelId,
            privacy_status: 'private',
            source: 'render_queue_admin_upload',
        }

        if (existingRow) {
            const { error: updateError } = await sb
                .from('publishing_requests')
                .update({ video_url: videoUrl, metadata: metadataPayload, status: 'approved' })
                .eq('id', existingRow.id)
            if (updateError) throw updateError
        } else {
            const { error: insertError } = await sb
                .from('publishing_requests')
                .insert({ user_id: profile.id, video_url: videoUrl, metadata: metadataPayload, status: 'approved' })
            if (insertError) throw insertError
        }

        auditLog('render_queue.upload_request', requester.user.email, {
            job_id: id,
            project_id: task.project_id,
            channel_id: channelId,
        })
        return NextResponse.json({ success: true })
    } catch (e: any) {
        return NextResponse.json({ error: e.message }, { status: 500 })
    }
}

export async function DELETE(req: Request) {
    const requester = await requireSuperAdmin(req)
    if (isAuthResponse(requester)) return requester

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
        auditLog('render_queue.delete', requester.user.email, { job_id: id })
        return NextResponse.json({ success: true })
    } catch (e: any) {
        return NextResponse.json({ error: e.message }, { status: 500 })
    }
}
