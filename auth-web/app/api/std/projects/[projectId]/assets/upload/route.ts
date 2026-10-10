import { isComicProject } from '@/lib/stdComic'
import { canEditStdAsset } from '@/lib/stdAssetEditPolicy'
import { queueSubmittedVideoReplacement } from '@/lib/stdSubmittedVideoReplacement'
import { cleanupReplacedSceneVideos } from '@/lib/stdReplacedVideoCleanup'
import { audioAssetStorageFields } from '@/lib/stdAudioMix'
import { NextResponse } from 'next/server'
import { supabaseAdmin } from '@/lib/supabaseAdmin'
import { requireStdUser } from '@/lib/stdWeb'
import { isStdRequiredClipScene, isStdVideoPromptScene, stdRequiredVideoSceneCount } from '@/lib/stdPolicy'
import { syncStdProjectToLegacy } from '@/lib/stdLegacySync'
import { buildStdGcsObjectPath, isGcsConfiguredAsync, uploadGcsBuffer } from '@/lib/gcsStorage'

export const dynamic = 'force-dynamic'
export const maxDuration = 300

const ASSET_TYPES = new Set(['image', 'video', 'audio', 'bgm', 'sfx', 'thumbnail', 'original'])
const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i

function sceneNumberOf(scene: any, index: number) {
    const value = Number(scene?.scene_number || scene?.scene_order || index + 1)
    return Number.isFinite(value) ? value : index + 1
}

function validMimeForAsset(assetType: string, mimeType: string): boolean {
    if (assetType === 'image' || assetType === 'thumbnail') return mimeType.startsWith('image/')
    if (assetType === 'video') return mimeType.startsWith('video/')
    if (assetType === 'audio' || assetType === 'bgm' || assetType === 'sfx') return mimeType.startsWith('audio/')
    return Boolean(mimeType)
}

function uploadedById(value: any): string | null {
    const id = String(value || '').trim()
    return UUID_RE.test(id) ? id : null
}

function upsertVisualAssetIntoScenes(scenes: any[], sceneNumber: number, assetType: string, asset: any, assetUrl: string) {
    const sourceScenes = Array.isArray(scenes) ? scenes : []
    const minimumLength = Math.max(sourceScenes.length, sceneNumber)
    const paddedScenes = Array.from({ length: minimumLength }, (_, index) => sourceScenes[index] || {
        scene_number: index + 1,
        scene_order: index + 1,
        scene_title: `Scene ${index + 1}`,
    })

    return paddedScenes.map((scene: any, index: number) => {
        const currentSceneNumber = sceneNumberOf(scene, index)
        if (currentSceneNumber !== sceneNumber) return scene
        const metadata = {
            ...(scene?.metadata || {}),
            [`${assetType}_asset_id`]: asset.id,
            [`${assetType}_gcs_path`]: asset?.metadata?.gcs_path || asset?.metadata?.storage_path || null,
            [`${assetType}_file_name`]: asset.file_name,
        }
        return {
            ...scene,
            scene_number: currentSceneNumber,
            scene_order: scene?.scene_order || currentSceneNumber,
            image_url: assetType === 'image' ? assetUrl : (scene?.image_url || scene?.image || null),
            video_url: assetType === 'video' ? assetUrl : (scene?.video_url || scene?.video || null),
            asset_status: 'ready',
            metadata,
        }
    })
}

function buildProjectPayloadWithVisualAsset(project: any, sceneNumber: number | null, assetType: string, asset: any) {
    if (sceneNumber == null || !['image', 'video'].includes(assetType)) return project.project_payload || {}
    const assetUrl = asset?.metadata?.storage_public_url
        || `/api/std/projects/${encodeURIComponent(project.id)}/assets/file?assetId=${encodeURIComponent(asset.id)}`
    const projectPayload = project.project_payload || {}
    const structure = projectPayload.structure || {}
    const payloadScenes = Array.isArray(projectPayload.scenes) ? projectPayload.scenes : []
    const structureScenes = Array.isArray(structure.scenes) ? structure.scenes : payloadScenes
    const nextStructureScenes = upsertVisualAssetIntoScenes(structureScenes, sceneNumber, assetType, asset, assetUrl)
    const nextPayloadScenes = upsertVisualAssetIntoScenes(
        payloadScenes.length > 0 ? payloadScenes : nextStructureScenes,
        sceneNumber,
        assetType,
        asset,
        assetUrl
    )

    return {
        ...projectPayload,
        scenes: nextPayloadScenes,
        structure: {
            ...structure,
            scenes: nextStructureScenes,
        },
    }
}

async function updateSceneAssetStatus(projectId: string, sceneNumber: number, project: any) {
    const { data: activeAssets } = await supabaseAdmin
        .from('std_project_assets')
        .select('id,asset_type')
        .eq('project_id', projectId)
        .eq('scene_number', sceneNumber)
        .in('asset_type', ['image', 'video'])
        .in('status', ['uploaded', 'assigned'])

    const isReady = isStdRequiredClipScene(sceneNumber, project)
        ? Boolean((activeAssets || []).some((asset: any) => asset.asset_type === 'video'))
        : Boolean(activeAssets && activeAssets.length > 0)

    await supabaseAdmin
        .from('std_project_scenes')
        .update({
            asset_status: isReady ? 'ready' : 'missing',
            updated_at: new Date().toISOString(),
        })
        .eq('project_id', projectId)
        .eq('scene_number', sceneNumber)
}

export async function POST(req: Request, { params }: { params: { projectId: string } }) {
    const auth = await requireStdUser(req)
    if (!auth.ok) return auth.response

    let form: FormData
    try {
        form = await req.formData()
    } catch {
        return NextResponse.json({ success: false, error: 'Invalid upload form data' }, { status: 400 })
    }

    const fileValue = form.get('file')
    if (!(fileValue instanceof File)) {
        return NextResponse.json({ success: false, error: 'File is required' }, { status: 400 })
    }

    const assetType = String(form.get('asset_type') || '').toLowerCase()
    const sceneRaw = form.get('scene_number')
    const sceneNumber = sceneRaw == null || String(sceneRaw).trim() === '' ? null : Number(sceneRaw)
    const mimeType = String(fileValue.type || form.get('mime_type') || 'application/octet-stream')

    if (!ASSET_TYPES.has(assetType)) return NextResponse.json({ success: false, error: 'Invalid asset type' }, { status: 400 })
    if (!validMimeForAsset(assetType, mimeType)) return NextResponse.json({ success: false, error: 'Invalid mime type for asset' }, { status: 400 })
    if (sceneNumber != null && !Number.isFinite(sceneNumber)) {
        return NextResponse.json({ success: false, error: 'Invalid scene number' }, { status: 400 })
    }
    const { data: project, error: projectError } = await supabaseAdmin
        .from('std_projects')
        .select('*')
        .eq('id', params.projectId)
        .eq('employee_email', auth.requester.email)
        .maybeSingle()

    if (projectError) return NextResponse.json({ success: false, error: projectError.message }, { status: 500 })
    if (!project) return NextResponse.json({ success: false, error: 'Project not found' }, { status: 404 })
    if (!canEditStdAsset(project, assetType, sceneNumber)) {
        return NextResponse.json({ success: false, error: 'Project is not editable' }, { status: 409 })
    }

    if (sceneNumber != null && isStdRequiredClipScene(sceneNumber, project) && assetType === 'image') {
        const requiredVideoSceneCount = stdRequiredVideoSceneCount(project)
        return NextResponse.json({
            success: false,
            error: `Video files are required for scenes 1-${requiredVideoSceneCount}.`,
            code: 'video_required_for_scene',
        }, { status: 422 })
    }
    if (
        sceneNumber != null
        && !isComicProject(project)
        && sceneNumber > stdRequiredVideoSceneCount(project)
        && ['image', 'video'].includes(assetType)
    ) {
        return NextResponse.json({
            success: false,
            error: `Image scenes after scene ${stdRequiredVideoSceneCount(project)} are protected and cannot be replaced.`,
            code: 'generated_image_scene_protected',
        }, { status: 422 })
    }

    let scene: any = null
    if (sceneNumber != null) {
        const { data: sceneRow, error: sceneError } = await supabaseAdmin
            .from('std_project_scenes')
            .select('id,scene_number')
            .eq('project_id', project.id)
            .eq('scene_number', sceneNumber)
            .maybeSingle()
        if (sceneError) return NextResponse.json({ success: false, error: sceneError.message }, { status: 500 })
        if (!sceneRow) {
            const payloadScenes = Array.isArray(project.project_payload?.structure?.scenes)
                ? project.project_payload.structure.scenes
                : (Array.isArray(project.project_payload?.scenes) ? project.project_payload.scenes : [])
            const payloadScene = payloadScenes.find((s: any, index: number) => sceneNumberOf(s, index) === sceneNumber) || {}
            const requiresVideoPrompt = isStdVideoPromptScene(sceneNumber, project)
            const { data: insertedScene, error: insertSceneError } = await supabaseAdmin
                .from('std_project_scenes')
                .insert({
                    project_id: project.id,
                    scene_number: sceneNumber,
                    scene_title: String(payloadScene.scene_title || payloadScene.title || `Scene ${sceneNumber}`).slice(0, 500),
                    scene_text: String(payloadScene.scene_text || payloadScene.script_excerpt || payloadScene.text || '').slice(0, 10000),
                    image_prompt: String(payloadScene.image_prompt || payloadScene.prompt || '').slice(0, 20000),
                    video_prompt: (requiresVideoPrompt || isComicProject(project)) ? String(payloadScene.video_prompt || '').slice(0, 20000) : '',
                    asset_status: 'missing',
                    metadata: {
                        ...(payloadScene.metadata || payloadScene || {}),
                        visual_type: requiresVideoPrompt ? (payloadScene.visual_type || 'video') : 'image',
                        video_prompt_required: requiresVideoPrompt,
                    },
                })
                .select('id,scene_number')
                .single()
            if (insertSceneError) return NextResponse.json({ success: false, error: insertSceneError.message }, { status: 500 })
            scene = insertedScene
        } else {
            scene = sceneRow
        }
    }

    try {
        const fileName = String(fileValue.name || form.get('file_name') || 'asset')
        const storagePath = buildStdGcsObjectPath({ projectId: project.id, sceneNumber, fileName })
        const buffer = Buffer.from(await fileValue.arrayBuffer())

        if (!(await isGcsConfiguredAsync())) {
            throw new Error('GCS storage is not configured')
        }
        const stored = await uploadGcsBuffer({ objectPath: storagePath, data: buffer, contentType: mimeType })

        let replacedVideos: any[] = []
        if (sceneNumber != null && ['image', 'video'].includes(assetType)) {
            if (assetType === 'video') {
                const previous = await supabaseAdmin.from('std_project_assets').select('id,metadata')
                    .eq('project_id', project.id).eq('scene_number', sceneNumber).eq('asset_type', 'video')
                    .in('status', ['uploaded', 'assigned'])
                if (previous.error) throw previous.error
                replacedVideos = previous.data || []
            }
            const { error: replaceError } = await supabaseAdmin
                .from('std_project_assets')
                .update({ status: 'replaced', updated_at: new Date().toISOString() })
                .eq('project_id', project.id)
                .eq('scene_number', sceneNumber)
                .eq('asset_type', assetType)
                .in('status', ['uploaded', 'assigned'])
            if (replaceError) throw replaceError
        }

        const { data: asset, error: assetError } = await supabaseAdmin
            .from('std_project_assets')
            .insert({
                project_id: project.id,
                scene_id: scene?.id || null,
                scene_number: sceneNumber,
                asset_type: audioAssetStorageFields(assetType).asset_type,
                drive_file_id: null,
                drive_folder_id: null,
                file_name: fileName,
                mime_type: mimeType,
                file_size: fileValue.size || null,
                status: sceneNumber != null ? 'assigned' : 'uploaded',
                uploaded_by: uploadedById(auth.requester.user.id),
                metadata: {
                    storage_provider: 'gcs',
                    storage_bucket: stored.bucket,
                    storage_path: stored.path,
                    storage_public_url: '',
                    gcs_bucket: stored.bucket,
                    gcs_path: stored.path,
                    upload_mode: 'server_gcs_storage',
                    ...audioAssetStorageFields(assetType).metadata,
                    uploaded_by: auth.requester.email,
                },
            })
            .select('*')
            .single()

        if (assetError) return NextResponse.json({ success: false, error: assetError.message }, { status: 500 })

        if (sceneNumber != null) {
            await updateSceneAssetStatus(project.id, sceneNumber, project)
        }

        const { count: readySceneCount } = await supabaseAdmin
            .from('std_project_scenes')
            .select('id', { count: 'exact', head: true })
            .eq('project_id', project.id)
            .eq('asset_status', 'ready')

        const progressPayload = project.progress_payload || {}
        const nextProjectPayload = buildProjectPayloadWithVisualAsset(project, sceneNumber, assetType, asset)

        const { error: projectUpdateError } = await supabaseAdmin
            .from('std_projects')
            .update({
                status: project.status === 'claimed' ? 'in_progress' : project.status,
                progress_payload: {
                    ...progressPayload,
                    ready_scene_count: readySceneCount || 0,
                    last_asset_uploaded_at: new Date().toISOString(),
                },
                project_payload: nextProjectPayload,
                updated_at: new Date().toISOString(),
            })
            .eq('id', project.id)
        if (projectUpdateError) throw projectUpdateError

        let postprocessWarning: string | null = null
        if (assetType === 'video' && sceneNumber != null && project.status === 'review_requested') {
            try {
                await queueSubmittedVideoReplacement(project, nextProjectPayload)
            } catch (error: any) {
                console.error('[STD VideoReplacement] AE queue failed:', error?.message)
                postprocessWarning = '영상은 교체됐지만 AIR 작업을 다시 예약하지 못했습니다. 프로젝트를 다시 제출해 주세요.'
            }
        }

        try {
            await syncStdProjectToLegacy(project.id)
        } catch (syncError: any) {
            console.error('[STD AssetUpload] legacy sync failed:', syncError?.message)
        }

        if (replacedVideos.length) {
            try {
                await cleanupReplacedSceneVideos(project.id, replacedVideos, asset)
            } catch (cleanupError: any) {
                console.error('[STD AssetUpload] replaced GCS video cleanup failed:', cleanupError?.message)
                postprocessWarning = [postprocessWarning, '영상은 교체됐지만 이전 GCS 파일을 삭제하지 못했습니다.'].filter(Boolean).join(' ')
            }
        }

        return NextResponse.json({
            success: true,
            postprocess_warning: postprocessWarning,
            asset: {
                ...asset,
                drive_file_link: null,
                drive_folder_link: null,
            },
            drive_backup_error: null,
        })
    } catch (error: any) {
        console.error('[STD AssetUpload] failed:', error?.message)
        return NextResponse.json({ success: false, error: error?.message || 'GCS upload failed' }, { status: 500 })
    }
}
