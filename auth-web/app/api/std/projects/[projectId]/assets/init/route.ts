import { NextResponse } from 'next/server'
import { supabaseAdmin } from '@/lib/supabaseAdmin'
import { requireStdUser } from '@/lib/stdWeb'
import { isStdRequiredVideoScene, STD_REQUIRED_VIDEO_SCENE_COUNT } from '@/lib/stdPolicy'
import {
    createStdDriveUploadSession,
    ensureStdProjectDriveFolders,
    folderForAssetType,
    sanitizeDriveName,
} from '@/lib/stdGoogleDrive'

export const dynamic = 'force-dynamic'

const ASSET_TYPES = new Set(['image', 'video', 'audio', 'bgm', 'sfx', 'thumbnail', 'original'])
const CONTENT_ASSETS_BUCKET = 'content-assets'

function validMimeForAsset(assetType: string, mimeType: string): boolean {
    if (assetType === 'image' || assetType === 'thumbnail') return mimeType.startsWith('image/')
    if (assetType === 'video') return mimeType.startsWith('video/')
    if (assetType === 'audio' || assetType === 'bgm' || assetType === 'sfx') return mimeType.startsWith('audio/')
    return Boolean(mimeType)
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

    const assetType = String(body?.asset_type || '').toLowerCase()
    const mimeType = String(body?.mime_type || '').trim()
    const fileName = sanitizeDriveName(String(body?.file_name || ''), 'asset')
    const fileSize = Number(body?.file_size || 0) || null
    const sceneNumber = body?.scene_number == null ? null : Number(body.scene_number)

    if (!ASSET_TYPES.has(assetType)) {
        return NextResponse.json({ success: false, error: 'Invalid asset type' }, { status: 400 })
    }
    if (!validMimeForAsset(assetType, mimeType)) {
        return NextResponse.json({ success: false, error: 'Invalid mime type for asset' }, { status: 400 })
    }
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
    if (
        sceneNumber != null
        && sceneNumber > STD_REQUIRED_VIDEO_SCENE_COUNT
        && ['image', 'video'].includes(assetType)
    ) {
        return NextResponse.json({
            success: false,
            error: 'Generated image scenes after scene 12 are protected and cannot be replaced.',
            code: 'generated_image_scene_protected',
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

    try {
        const storagePath = [
            'std-projects',
            project.id,
            sceneNumber == null ? 'project-assets' : `scenes/${Math.floor(sceneNumber)}`,
            `${Date.now()}-${fileName}`,
        ].join('/')
        const { data: signedUpload, error: storageError } = await supabaseAdmin.storage
            .from(CONTENT_ASSETS_BUCKET)
            .createSignedUploadUrl(storagePath, { upsert: true })
        if (storageError || !signedUpload?.signedUrl) {
            throw new Error(storageError?.message || 'Supabase Storage upload URL could not be created')
        }
        const { data: publicUrlData } = supabaseAdmin.storage
            .from(CONTENT_ASSETS_BUCKET)
            .getPublicUrl(storagePath)

        // Each visual file is retained in both stores: Storage for playback and
        // Drive as the project archive. Create the Drive session before returning
        // so the browser can fail cleanly instead of creating a one-sided asset.
        const folders = await ensureStdProjectDriveFolders(project)
        const uploadUrl = await createStdDriveUploadSession({
            folderId: folderForAssetType(folders, assetType),
            fileName,
            mimeType,
            fileSize,
        })
        const progressPayload = project.progress_payload || {}
        await supabaseAdmin
            .from('std_projects')
            .update({
                drive_folder_id: folders.projectFolderId,
                progress_payload: {
                    ...progressPayload,
                    std_drive: {
                        ...(progressPayload.std_drive || {}),
                        folder_ids: {
                            project: folders.projectFolderId,
                            images: folders.imagesFolderId,
                            videos: folders.videosFolderId,
                            originals: folders.originalsFolderId,
                            audio: folders.audioFolderId,
                        },
                    },
                },
                updated_at: new Date().toISOString(),
            })
            .eq('id', project.id)

        return NextResponse.json({
            success: true,
            storage_upload_url: signedUpload.signedUrl,
            storage_bucket: CONTENT_ASSETS_BUCKET,
            storage_path: storagePath,
            storage_public_url: publicUrlData.publicUrl,
            upload_url: uploadUrl,
            drive_folder_id: folders.projectFolderId,
            target_folder_id: folderForAssetType(folders, assetType),
            file_name: fileName,
            asset_type: assetType,
            scene_number: sceneNumber,
        })
    } catch (error: any) {
        return NextResponse.json({ success: false, error: error?.message || 'Drive upload init failed' }, { status: 500 })
    }
}
