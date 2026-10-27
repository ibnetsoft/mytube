import { hasSubmittedVideoPostwork } from '@/lib/stdSubmittedVideoPostwork'
import { isNonverbalProject, hasReadyNonverbalPlan } from '@/lib/stdNonverbal'
import { loadStdProjectAssets } from '@/lib/stdProjectAssets'
import { NextResponse } from 'next/server'
import { supabaseAdmin } from '@/lib/supabaseAdmin'
import { requireStdUser } from '@/lib/stdWeb'
import { isStdVideoPromptScene } from '@/lib/stdPolicy'
import { editableThumbnailError } from '@/lib/stdThumbnailRender'
import { syncStdProjectToLegacy } from '@/lib/stdLegacySync'
import { enqueueStdProjectRender, ensureStdGeneratedSceneAssetsArchived } from '@/lib/stdRenderQueue'
import { aeMouthApplicable } from '@/lib/stdAeMouth'
import { registerSubmissionPipeline } from '@/lib/stdSubmissionPipeline'
import { preparedAeScenes } from '@/lib/stdAeScenePreparation'
import { motionAutomationEnabled,registerMotionAutomation } from '@/lib/stdMotionAutomation'
import { productionEngineError } from '@/lib/stdProductionEnginePolicy'
import {motionProductionMethod} from '@/lib/stdMotionStudio'

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
    const engineError = productionEngineError(project)
    if (engineError) return NextResponse.json({success:false,code:'alternative_engine_disabled',error:engineError},{status:409})
    if (motionProductionMethod(project)==='motion_studio') {
        return NextResponse.json({ success: false, code: 'web_motion_export_required',
            error: 'Motion Studio에서 최종 MP4를 제작·저장한 뒤 «관리자 검수 요청»을 눌러 주세요. 웹 제작은 로컬 AE 워커로 제출하지 않습니다.',
        }, { status: 409 })
    }
    if (['effectcraft','filmcraft'].includes(motionProductionMethod(project))&&!motionAutomationEnabled(project)) {
        return NextResponse.json({success:false,error:'선택한 렌더러의 제출 후 자동 제작 설정을 켜고 저장해 주세요.'},{status:409})
    }
    const thumbnailError = motionAutomationEnabled(project) ? null : editableThumbnailError(
        project.project_payload?.thumbnail_design || project.progress_payload?.thumbnail_design,
        project.project_payload?.thumbnail_url || project.progress_payload?.thumbnail_url,
        true,
    )
    if (thumbnailError) return NextResponse.json({ success: false, error: thumbnailError }, { status: 409 })
    if (project.topic_queue_id && !project.submitted_at) {
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

    const [{ data: fetchedScenes, error: scenesError }, { data: loadedAssets, error: assetsError }] = await Promise.all([
        supabaseAdmin
            .from('std_project_scenes')
            .select('*')
            .eq('project_id', project.id).order('scene_number'),
        loadStdProjectAssets(supabaseAdmin, project.id, '*'),
    ])

    if (scenesError) return NextResponse.json({ success: false, error: scenesError.message }, { status: 500 })
    if (assetsError) return NextResponse.json({ success: false, error: assetsError.message }, { status: 500 })
    const scenes = [...(fetchedScenes || [])].sort((a: any, b: any) => Number(a.scene_number) - Number(b.scene_number))

    if (!scenes?.length) {
        return NextResponse.json({
            success: false,
            error: 'Project has no scenes to render',
        }, { status: 409 })
    }
    if (!isNonverbalProject(project) && project.progress_payload?.script_changed_requires_audio_regeneration) {
        return NextResponse.json({
            success: false,
            error: '대본이 변경되었습니다. 새 대본으로 TTS를 다시 생성한 뒤 렌더링해 주세요.',
        }, { status: 409 })
    }

    let assets = loadedAssets || []
    try {
        if(!motionAutomationEnabled(project)&&!hasSubmittedVideoPostwork(project,scenes||[],assets)) assets = await ensureStdGeneratedSceneAssetsArchived(project, scenes || [], assets)
        if (!isNonverbalProject(project)) assets = await recoverStoredTtsAsset(project, assets)
    } catch (archiveError: any) {
        return NextResponse.json({
            success: false,
            error: archiveError?.message || 'Failed to prepare stored assets for render',
        }, { status: 500 })
    }

    // Freeze prepared originals and finalized voice; the unified worker only executes them.
    if(motionAutomationEnabled(project)||hasSubmittedVideoPostwork(project,scenes||[],assets)) {
        try { const run=await registerMotionAutomation(project,scenes,assets,auth.requester.user.id)
            return NextResponse.json({success:true,...run,postprocess_pending:true,motion_automation:true,
                message:'제출 완료. 원본 영상·확정 음성을 유지해 AE 입모양·효과를 후작업하고 검수 통과 후 최종 렌더링을 자동 진행합니다.'},{status:202})
        } catch(error:any) { return NextResponse.json({success:false,error:error.message},{status:409}) }
    }
    let preparedScenes: Map<number, any>
    try {
        preparedScenes = preparedAeScenes(project, scenes, assets)
    } catch (error: any) {
        return NextResponse.json({ success: false, error: error.message || 'AE 장면 준비를 확인해 주세요.' }, { status: 409 })
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
        if (preparedScenes.has(sceneNumber)) return false
        if (isNonverbalProject(project)) return !hasReadyNonverbalPlan(project) || !visualAssets.some((a: any) =>
            Number(a.scene_number) === sceneNumber && a.asset_type === 'video' && hasStoredAssetFile(a)
            && !a.metadata?.region_motion_plan_id)
        return isStdVideoPromptScene(sceneNumber, project)
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
                .filter((sceneNumber: number) => !preparedScenes.has(sceneNumber) && isStdVideoPromptScene(sceneNumber, project)),
        }, { status: 409 })
    }

    const hasAudioAsset = (assets || []).some((asset: any) =>
        String(asset.asset_type || '').toLowerCase() === 'audio'
        && hasStoredAssetFile(asset)
    )
    if (!isNonverbalProject(project) && !hasAudioAsset) {
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

    const mouthRequired = project.project_payload?.ae_mouth?.enabled !== false && aeMouthApplicable(project, scenes || [], assets)
    const plannedScenes = Array.isArray(project.project_payload?.structure?.scenes)
        ? project.project_payload.structure.scenes.filter((scene: any) =>
            scene?.ae_effect_plan?.enabled || scene?.ae_motion_plan?.enabled) : []
    const needsPayloadUpdate = (mouthRequired && !project.project_payload?.ae_mouth?.enabled)
        || (plannedScenes.length > 0 && project.project_payload?.ae_scene_delivery !== 'gcs')
    if (needsPayloadUpdate) {
        const nextPayload = {
            ...project.project_payload,
            ...(mouthRequired ? { ae_mouth: { ...(project.project_payload?.ae_mouth || {}), enabled: true, first_scene: 19 } } : {}),
            ...(plannedScenes.length > 0 ? { ae_scene_delivery: 'gcs' } : {}),
        }
        const enabledAt = new Date().toISOString()
        const enabled = await supabaseAdmin.from('std_projects')
            .update({ project_payload: nextPayload, updated_at: enabledAt })
            .eq('id', project.id).eq('updated_at', project.updated_at).select('*').maybeSingle()
        if (enabled.error || !enabled.data) {
            return NextResponse.json({ success: false, error: '프로젝트가 변경되었습니다. 다시 제출해 주세요.' }, { status: 409 })
        }
        project.project_payload = nextPayload
        project.updated_at = enabled.data.updated_at || enabledAt
    }

    try {
        const run = await registerSubmissionPipeline(project, scenes || [], assets, auth.requester.user.id, mouthRequired || preparedScenes.size > 0)
        return NextResponse.json({ success: true, ...run, postprocess_pending: true,
            pipeline_version: 2, message: '제출 완료. 저장한 영상·음향 설정으로 자동 렌더링이 진행됩니다.' }, { status: 202 })
    } catch (error: any) {
        return NextResponse.json({ success: false, error: error.message || '제출 등록 실패' }, { status: 409 })
    }
}
