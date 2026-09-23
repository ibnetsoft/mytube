import { NextResponse } from 'next/server'
import { supabaseAdmin } from '@/lib/supabaseAdmin'
import { requireStdUser } from '@/lib/stdWeb'
import { isStdRequiredVideoScene } from '@/lib/stdPolicy'
import { editableThumbnailError } from '@/lib/stdThumbnailRender'
import { syncStdProjectToLegacy } from '@/lib/stdLegacySync'
import { enqueueStdProjectRender, ensureStdGeneratedSceneAssetsArchived } from '@/lib/stdRenderQueue'

export const dynamic = 'force-dynamic'

function hasStoredAssetFile(asset: any): boolean {
    const metadata = asset?.metadata && typeof asset.metadata === 'object' ? asset.metadata : {}
    const nestedMetadata = metadata?.metadata && typeof metadata.metadata === 'object' ? metadata.metadata : {}
    return Boolean(
        String(asset?.drive_file_id || '').trim()
        || String(metadata?.storage_path || metadata?.storage_object_path || nestedMetadata?.storage_path || nestedMetadata?.storage_object_path || '').trim()
        || String(metadata?.gcs_path || nestedMetadata?.gcs_path || '').trim()
    )
}

function extractAssetIdFromUrl(value: any): string {
    const url = String(value || '').trim()
    if (!url) return ''
    try {
        const parsed = new URL(url, 'https://studio.airing.work')
        return String(parsed.searchParams.get('assetId') || '').trim()
    } catch {
        const match = url.match(/[?&]assetId=([^&]+)/)
        return match ? decodeURIComponent(match[1]) : ''
    }
}

async function recoverStoredTtsAsset(project: any, assets: any[]) {
    const activeAssets = Array.isArray(assets) ? [...assets] : []
    const hasActiveAudio = activeAssets.some((asset: any) =>
        String(asset?.asset_type || '').toLowerCase() === 'audio'
        && hasStoredAssetFile(asset)
    )
    if (hasActiveAudio) return activeAssets

    const candidates = [
        project?.progress_payload?.tts_asset_id,
        project?.progress_payload?.audio_asset_id,
        project?.project_payload?.tts_asset_id,
        project?.project_payload?.audio_asset_id,
        extractAssetIdFromUrl(project?.project_payload?.audio_url || project?.project_payload?.tts_url),
    ].map((value: any) => String(value || '').trim()).filter(Boolean)

    let recovered: any = null
    if (candidates.length > 0) {
        const { data, error } = await supabaseAdmin
            .from('std_project_assets')
            .select('*')
            .eq('project_id', project.id)
            .eq('asset_type', 'audio')
            .in('id', Array.from(new Set(candidates)))
            .order('updated_at', { ascending: false })
            .limit(1)
        if (error) throw error
        recovered = (data || []).find(hasStoredAssetFile) || null
    }

    if (!recovered && (project?.progress_payload?.has_tts_audio || project?.progress_payload?.tts_completed || project?.project_payload?.audio_url || project?.project_payload?.tts_url)) {
        const { data, error } = await supabaseAdmin
            .from('std_project_assets')
            .select('*')
            .eq('project_id', project.id)
            .eq('asset_type', 'audio')
            .order('updated_at', { ascending: false })
            .limit(5)
        if (error) throw error
        recovered = (data || []).find(hasStoredAssetFile) || null
    }

    if (!recovered) return activeAssets
    if (!['uploaded', 'assigned'].includes(String(recovered.status || ''))) {
        const { data, error } = await supabaseAdmin
            .from('std_project_assets')
            .update({ status: 'uploaded', updated_at: new Date().toISOString() })
            .eq('id', recovered.id)
            .select('*')
            .single()
        if (error) throw error
        recovered = data || recovered
    }
    const index = activeAssets.findIndex((asset: any) => String(asset?.id || '') === String(recovered.id || ''))
    if (index >= 0) activeAssets[index] = recovered
    else activeAssets.push(recovered)
    return activeAssets
}

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
    if (project.submitted_at) {
        return NextResponse.json({ success: true, already_submitted: true, submitted_at: project.submitted_at })
    }
    const thumbnailError = editableThumbnailError(
        project.project_payload?.thumbnail_design || project.progress_payload?.thumbnail_design,
        project.project_payload?.thumbnail_url || project.progress_payload?.thumbnail_url,
        true,
    )
    if (thumbnailError) return NextResponse.json({ success: false, error: thumbnailError }, { status: 409 })
    if (project.topic_queue_id) {
        const { data: sharedSubmission, error: sharedSubmissionError } = await supabaseAdmin
            .from('std_projects')
            .select('id,submitted_at')
            .eq('topic_queue_id', project.topic_queue_id)
            .neq('id', project.id)
            .not('submitted_at', 'is', null)
            .order('submitted_at', { ascending: false })
            .limit(1)
            .maybeSingle()
        if (sharedSubmissionError) return NextResponse.json({ success: false, error: sharedSubmissionError.message }, { status: 500 })
        if (sharedSubmission) {
            return NextResponse.json({
                success: true,
                shared_submission: true,
                submitted_at: sharedSubmission.submitted_at,
                shared_project_id: sharedSubmission.id,
            })
        }
    }

    const [{ data: scenes, error: scenesError }, { data: loadedAssets, error: assetsError }] = await Promise.all([
        supabaseAdmin
            .from('std_project_scenes')
            .select('*')
            .eq('project_id', project.id),
        supabaseAdmin
            .from('std_project_assets')
            .select('*')
            .eq('project_id', project.id)
            .in('asset_type', ['image', 'video', 'audio', 'bgm', 'sfx', 'thumbnail', 'other'])
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
    if (project.progress_payload?.script_changed_requires_audio_regeneration) {
        return NextResponse.json({
            success: false,
            error: '대본이 변경되었습니다. 새 대본으로 TTS를 다시 생성한 뒤 렌더링해 주세요.',
        }, { status: 409 })
    }

    let assets = loadedAssets || []
    try {
        assets = await ensureStdGeneratedSceneAssetsArchived(project, scenes || [], assets)
        assets = await recoverStoredTtsAsset(project, assets)
    } catch (archiveError: any) {
        return NextResponse.json({
            success: false,
            error: archiveError?.message || 'Failed to prepare stored assets for render',
        }, { status: 500 })
    }

    const visualAssets = assets.filter((asset: any) => ['image', 'video'].includes(String(asset.asset_type || '').toLowerCase()))
    const activeSceneNumbers = new Set(visualAssets.map((asset: any) => Number(asset.scene_number)).filter(Number.isFinite))
    const activeVideoSceneNumbers = new Set(
        visualAssets
            .filter((asset: any) => asset.asset_type === 'video')
            .map((asset: any) => Number(asset.scene_number))
            .filter(Number.isFinite)
    )
    const missingScenes = (scenes || []).filter((scene: any) => {
        const sceneNumber = Number(scene.scene_number)
        return isStdRequiredVideoScene(sceneNumber, project)
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
                .filter((sceneNumber: number) => isStdRequiredVideoScene(sceneNumber, project)),
        }, { status: 409 })
    }

    const hasAudioAsset = (assets || []).some((asset: any) =>
        String(asset.asset_type || '').toLowerCase() === 'audio'
        && hasStoredAssetFile(asset)
    )
    if (!hasAudioAsset) {
        return NextResponse.json({
            success: false,
            error: 'TTS audio is required before submitting for render',
        }, { status: 409 })
    }

    const hasThumbnailAsset = (assets || []).some((asset: any) =>
        String(asset.asset_type || '').toLowerCase() === 'thumbnail'
        && hasStoredAssetFile(asset)
    )
    if (!hasThumbnailAsset) {
        return NextResponse.json({
            success: false,
            error: 'Thumbnail is required before submitting for render',
        }, { status: 409 })
    }

    const submittedAt = new Date().toISOString()
    const { data: submissionClaim, error: submissionClaimError } = await supabaseAdmin
        .from('std_projects')
        .update({
            status: 'review_requested',
            submitted_at: submittedAt,
            updated_at: submittedAt,
        })
        .eq('id', project.id)
        .is('submitted_at', null)
        .select('id')
        .maybeSingle()

    if (submissionClaimError) {
        return NextResponse.json({ success: false, error: submissionClaimError.message }, { status: 500 })
    }
    if (!submissionClaim) {
        return NextResponse.json({ success: true, already_submitted: true })
    }

    const releaseSubmissionClaim = async () => {
        await supabaseAdmin
            .from('std_projects')
            .update({
                status: project.status,
                submitted_at: null,
                updated_at: new Date().toISOString(),
            })
            .eq('id', project.id)
            .eq('submitted_at', submittedAt)
    }

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

    if (submissionError) {
        await releaseSubmissionClaim()
        return NextResponse.json({ success: false, error: submissionError.message }, { status: 500 })
    }

    let renderQueueRow: any = null
    try {
        renderQueueRow = await enqueueStdProjectRender(project.id)
    } catch (queueError: any) {
        await releaseSubmissionClaim()
        return NextResponse.json({ success: false, error: queueError?.message || 'Failed to enqueue render job' }, { status: 500 })
    }

    const renderVersion = Number(renderQueueRow?.metadata?.render_version || renderQueueRow?.render_version || 1)
    await supabaseAdmin
        .from('std_project_submissions')
        .update({
            metadata: {
                scene_count: scenes?.length || 0,
                asset_count: assets?.length || 0,
                render_version: renderVersion,
                remote_render_queue_id: renderQueueRow?.id || null,
            },
        })
        .eq('id', submission.id)

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
                remote_render_mode: renderQueueRow?.render_mode || 'gcs_api',
                remote_asset_file_id: renderQueueRow?.asset_file_id || null,
                remote_asset_file_name: renderQueueRow?.asset_file_name || null,
                latest_render_version: renderVersion,
                editing_render_version: null,
                rerender_draft: false,
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

    return NextResponse.json({ success: true, submission, render_queue: renderQueueRow, render_version: renderVersion })
}
