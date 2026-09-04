import { NextResponse } from 'next/server'
import { supabaseAdmin } from '@/lib/supabaseAdmin'
import { requireStdUser } from '@/lib/stdWeb'
import { isStdRequiredVideoScene } from '@/lib/stdPolicy'
import { driveFileLink, driveFolderLink, getStdDriveFileMetadata } from '@/lib/stdGoogleDrive'
import { syncStdProjectToLegacy } from '@/lib/stdLegacySync'

export const dynamic = 'force-dynamic'

const ASSET_TYPES = new Set(['image', 'video', 'audio', 'bgm', 'sfx', 'thumbnail', 'original'])

function sceneNumberOf(scene: any, index: number) {
    const value = Number(scene?.scene_number || scene?.scene_order || index + 1)
    return Number.isFinite(value) ? value : index + 1
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
            [`${assetType}_drive_file_id`]: asset.drive_file_id,
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
    const assetUrl = asset?.metadata?.thumbnail_link
        || asset?.metadata?.web_view_link
        || driveFileLink(asset?.drive_file_id)
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

async function updateSceneAssetStatus(projectId: string, sceneNumber: number) {
    const { data: activeAssets } = await supabaseAdmin
        .from('std_project_assets')
        .select('id,asset_type')
        .eq('project_id', projectId)
        .eq('scene_number', sceneNumber)
        .in('asset_type', ['image', 'video'])
        .in('status', ['uploaded', 'assigned'])

    const isReady = isStdRequiredVideoScene(sceneNumber)
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

    let body: any
    try {
        body = await req.json()
    } catch {
        return NextResponse.json({ success: false, error: 'Invalid JSON' }, { status: 400 })
    }

    const driveFileId = String(body?.drive_file_id || '').trim()
    const localRelativePath = String(body?.local_relative_path || '').trim().slice(0, 2000)
    const assetType = String(body?.asset_type || '').toLowerCase()
    const sceneNumber = body?.scene_number == null ? null : Number(body.scene_number)
    const targetFolderId = String(body?.target_folder_id || '').trim()

    if (!driveFileId) return NextResponse.json({ success: false, error: 'Drive file id is required' }, { status: 400 })
    if (!ASSET_TYPES.has(assetType)) return NextResponse.json({ success: false, error: 'Invalid asset type' }, { status: 400 })
    if (sceneNumber != null && !Number.isFinite(sceneNumber)) {
        return NextResponse.json({ success: false, error: 'Invalid scene number' }, { status: 400 })
    }
    if (sceneNumber != null && isStdRequiredVideoScene(sceneNumber) && assetType === 'image') {
        return NextResponse.json({
            success: false,
            error: 'Video file is required for scenes 1-12.',
            code: 'video_required_for_scene',
        }, { status: 422 })
    }

    const { data: project, error: projectError } = await supabaseAdmin
        .from('std_projects')
        .select('*')
        .eq('id', params.projectId)
        .eq('employee_email', auth.requester.email)
        .maybeSingle()

    if (projectError) return NextResponse.json({ success: false, error: projectError.message }, { status: 500 })
    if (!project) return NextResponse.json({ success: false, error: 'Project not found' }, { status: 404 })
    if (['review_requested', 'approved', 'canceled'].includes(project.status)) {
        return NextResponse.json({ success: false, error: 'Project is not editable' }, { status: 409 })
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
            const requiresVideoPrompt = isStdRequiredVideoScene(sceneNumber)
            const { data: insertedScene, error: insertSceneError } = await supabaseAdmin
                .from('std_project_scenes')
                .insert({
                    project_id: project.id,
                    scene_number: sceneNumber,
                    scene_title: String(payloadScene.scene_title || payloadScene.title || `Scene ${sceneNumber}`).slice(0, 500),
                    scene_text: String(payloadScene.scene_text || payloadScene.script_excerpt || payloadScene.text || '').slice(0, 10000),
                    image_prompt: String(payloadScene.image_prompt || payloadScene.prompt || '').slice(0, 20000),
                    video_prompt: requiresVideoPrompt ? String(payloadScene.video_prompt || '').slice(0, 20000) : '',
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
        const metadata = await getStdDriveFileMetadata(driveFileId)
        if (targetFolderId && Array.isArray(metadata.parents) && !metadata.parents.includes(targetFolderId)) {
            return NextResponse.json({ success: false, error: 'Drive file is not in the expected folder' }, { status: 400 })
        }

        if (sceneNumber != null && ['image', 'video'].includes(assetType)) {
            await supabaseAdmin
                .from('std_project_assets')
                .update({ status: 'replaced', updated_at: new Date().toISOString() })
                .eq('project_id', project.id)
                .eq('scene_number', sceneNumber)
                .eq('asset_type', assetType)
                .in('status', ['uploaded', 'assigned'])
        }

        const { data: asset, error: assetError } = await supabaseAdmin
            .from('std_project_assets')
            .insert({
                project_id: project.id,
                scene_id: scene?.id || null,
                scene_number: sceneNumber,
                asset_type: assetType,
                drive_file_id: metadata.id,
                drive_folder_id: targetFolderId || metadata.parents?.[0] || project.drive_folder_id,
                file_name: metadata.name || body?.file_name || 'asset',
                mime_type: metadata.mimeType || body?.mime_type || null,
                file_size: metadata.size ? Number(metadata.size) : Number(body?.file_size || 0) || null,
                status: sceneNumber != null ? 'assigned' : 'uploaded',
                uploaded_by: auth.requester.user.id,
                metadata: {
                    web_view_link: metadata.webViewLink || driveFileLink(metadata.id),
                    thumbnail_link: metadata.thumbnailLink || null,
                    local_relative_path: localRelativePath || null,
                    local_storage_mode: localRelativePath ? 'browser_directory' : null,
                    uploaded_by: auth.requester.email,
                },
            })
            .select('*')
            .single()

        if (assetError) return NextResponse.json({ success: false, error: assetError.message }, { status: 500 })

        if (sceneNumber != null) {
            await updateSceneAssetStatus(project.id, sceneNumber)
        }

        const { count: readySceneCount } = await supabaseAdmin
            .from('std_project_scenes')
            .select('id', { count: 'exact', head: true })
            .eq('project_id', project.id)
            .eq('asset_status', 'ready')

        const progressPayload = project.progress_payload || {}
        const nextProjectPayload = buildProjectPayloadWithVisualAsset(project, sceneNumber, assetType, asset)

        await supabaseAdmin
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

        try {
            await syncStdProjectToLegacy(project.id)
        } catch (syncError: any) {
            console.error('[STD AssetComplete] legacy sync failed:', syncError?.message)
        }

        return NextResponse.json({
            success: true,
            asset: {
                ...asset,
                drive_file_link: driveFileLink(metadata.id),
                drive_folder_link: asset.drive_folder_id ? driveFolderLink(asset.drive_folder_id) : null,
            },
        })
    } catch (error: any) {
        return NextResponse.json({ success: false, error: error?.message || 'Drive upload complete failed' }, { status: 500 })
    }
}
