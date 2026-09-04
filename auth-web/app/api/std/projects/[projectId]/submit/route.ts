import { NextResponse } from 'next/server'
import { supabaseAdmin } from '@/lib/supabaseAdmin'
import { requireStdUser } from '@/lib/stdWeb'
import { isStdRequiredVideoScene } from '@/lib/stdPolicy'
import { syncStdProjectToLegacy } from '@/lib/stdLegacySync'
import { enqueueStdProjectRender } from '@/lib/stdRenderQueue'

export const dynamic = 'force-dynamic'

export async function POST(req: Request, { params }: { params: { projectId: string } }) {
    const auth = await requireStdUser(req)
    if (!auth.ok) return auth.response

    const { data: project, error: projectError } = await supabaseAdmin
        .from('std_projects')
        .select('*')
        .eq('id', params.projectId)
        .eq('employee_email', auth.requester.email)
        .maybeSingle()

    if (projectError) return NextResponse.json({ success: false, error: projectError.message }, { status: 500 })
    if (!project) return NextResponse.json({ success: false, error: 'Project not found' }, { status: 404 })
    if (['approved', 'canceled'].includes(project.status)) {
        return NextResponse.json({ success: false, error: 'Project is closed' }, { status: 409 })
    }

    const [{ data: scenes, error: scenesError }, { data: assets, error: assetsError }] = await Promise.all([
        supabaseAdmin
            .from('std_project_scenes')
            .select('id,scene_number')
            .eq('project_id', project.id),
        supabaseAdmin
            .from('std_project_assets')
            .select('id,scene_number,asset_type,status,drive_file_id')
            .eq('project_id', project.id)
            .in('asset_type', ['image', 'video', 'audio', 'bgm', 'sfx', 'thumbnail'])
            .in('status', ['uploaded', 'assigned']),
    ])

    if (scenesError) return NextResponse.json({ success: false, error: scenesError.message }, { status: 500 })
    if (assetsError) return NextResponse.json({ success: false, error: assetsError.message }, { status: 500 })

    if (!scenes?.length) {
        return NextResponse.json({
            success: false,
            error: 'Project has no scenes to render',
        }, { status: 409 })
    }

    const visualAssets = (assets || []).filter((asset: any) => ['image', 'video'].includes(String(asset.asset_type || '').toLowerCase()))
    const activeSceneNumbers = new Set(visualAssets.map((asset: any) => Number(asset.scene_number)).filter(Number.isFinite))
    const activeVideoSceneNumbers = new Set(
        visualAssets
            .filter((asset: any) => asset.asset_type === 'video')
            .map((asset: any) => Number(asset.scene_number))
            .filter(Number.isFinite)
    )
    const missingScenes = (scenes || []).filter((scene: any) => {
        const sceneNumber = Number(scene.scene_number)
        return isStdRequiredVideoScene(sceneNumber)
            ? !activeVideoSceneNumbers.has(sceneNumber)
            : !activeSceneNumbers.has(sceneNumber)
    })
    if (missingScenes.length > 0) {
        return NextResponse.json({
            success: false,
            error: 'Some scenes do not have required uploaded assets',
            missing_scene_numbers: missingScenes.map((scene: any) => scene.scene_number),
            required_video_scene_numbers: (scenes || [])
                .map((scene: any) => Number(scene.scene_number))
                .filter((sceneNumber: number) => isStdRequiredVideoScene(sceneNumber)),
        }, { status: 409 })
    }

    const hasAudioAsset = (assets || []).some((asset: any) =>
        String(asset.asset_type || '').toLowerCase() === 'audio'
        && String(asset.drive_file_id || '').trim()
    )
    if (!hasAudioAsset) {
        return NextResponse.json({
            success: false,
            error: 'TTS audio is required before submitting for render',
        }, { status: 409 })
    }

    const hasThumbnailAsset = (assets || []).some((asset: any) =>
        String(asset.asset_type || '').toLowerCase() === 'thumbnail'
        && String(asset.drive_file_id || '').trim()
    )
    if (!hasThumbnailAsset) {
        return NextResponse.json({
            success: false,
            error: 'Thumbnail is required before submitting for render',
        }, { status: 409 })
    }

    const submittedAt = new Date().toISOString()
    const { data: submission, error: submissionError } = await supabaseAdmin
        .from('std_project_submissions')
        .insert({
            project_id: project.id,
            submitted_by: auth.requester.user.id,
            status: 'review_requested',
            metadata: {
                scene_count: scenes?.length || 0,
                asset_count: assets?.length || 0,
            },
        })
        .select('*')
        .single()

    if (submissionError) return NextResponse.json({ success: false, error: submissionError.message }, { status: 500 })

    let renderQueueRow: any = null
    try {
        renderQueueRow = await enqueueStdProjectRender(project.id)
    } catch (queueError: any) {
        return NextResponse.json({ success: false, error: queueError?.message || 'Failed to enqueue render job' }, { status: 500 })
    }

    await supabaseAdmin
        .from('std_projects')
        .update({
            status: 'review_requested',
            submitted_at: submittedAt,
            progress_payload: {
                ...(project.progress_payload || {}),
                submitted_at: submittedAt,
                submitted_asset_count: assets?.length || 0,
                remote_task_id: renderQueueRow?.id || null,
                remote_render_queue_id: renderQueueRow?.id || null,
                remote_render_mode: renderQueueRow?.render_mode || 'drive_api',
                remote_asset_file_id: renderQueueRow?.asset_file_id || null,
                remote_asset_file_name: renderQueueRow?.asset_file_name || null,
                admin_publish_status: 'render_pending',
                submitted_to_render_queue_at: submittedAt,
            },
            updated_at: submittedAt,
        })
        .eq('id', project.id)

    try {
        await syncStdProjectToLegacy(project.id)
    } catch (syncError: any) {
        console.error('[STD Submit] legacy sync failed:', syncError?.message)
    }

    return NextResponse.json({ success: true, submission, render_queue: renderQueueRow })
}
