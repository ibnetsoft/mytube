import { NextResponse } from 'next/server'
import { supabaseAdmin } from '@/lib/supabaseAdmin'
import { requireStdUser } from '@/lib/stdWeb'
import { driveFileLink, driveFolderLink, getStdDriveFileMetadata } from '@/lib/stdGoogleDrive'
import { syncStdProjectToLegacy } from '@/lib/stdLegacySync'

export const dynamic = 'force-dynamic'

const ASSET_TYPES = new Set(['image', 'video', 'audio', 'thumbnail', 'original'])

async function updateSceneAssetStatus(projectId: string, sceneNumber: number) {
    const { data: activeAssets } = await supabaseAdmin
        .from('std_project_assets')
        .select('id')
        .eq('project_id', projectId)
        .eq('scene_number', sceneNumber)
        .in('asset_type', ['image', 'video'])
        .in('status', ['uploaded', 'assigned'])

    await supabaseAdmin
        .from('std_project_scenes')
        .update({
            asset_status: activeAssets && activeAssets.length > 0 ? 'ready' : 'missing',
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
    const assetType = String(body?.asset_type || '').toLowerCase()
    const sceneNumber = body?.scene_number == null ? null : Number(body.scene_number)
    const targetFolderId = String(body?.target_folder_id || '').trim()

    if (!driveFileId) return NextResponse.json({ success: false, error: 'Drive file id is required' }, { status: 400 })
    if (!ASSET_TYPES.has(assetType)) return NextResponse.json({ success: false, error: 'Invalid asset type' }, { status: 400 })
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
        if (!sceneRow) return NextResponse.json({ success: false, error: 'Scene not found' }, { status: 404 })
        scene = sceneRow
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
        await supabaseAdmin
            .from('std_projects')
            .update({
                status: project.status === 'claimed' ? 'in_progress' : project.status,
                progress_payload: {
                    ...progressPayload,
                    ready_scene_count: readySceneCount || 0,
                    last_asset_uploaded_at: new Date().toISOString(),
                },
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
