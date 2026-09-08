import { NextResponse } from 'next/server'
import { supabaseAdmin } from '@/lib/supabaseAdmin'
import { requireStdUser } from '@/lib/stdWeb'
import { isStdRequiredVideoScene, STD_REQUIRED_VIDEO_SCENE_COUNT } from '@/lib/stdPolicy'
import {
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

        // Drive is archived server-side after Storage is committed. Sending a
        // resumable Drive URL to the browser causes a CORS-blocked PUT.

        return NextResponse.json({
            success: true,
            storage_upload_url: signedUpload.signedUrl,
            storage_bucket: CONTENT_ASSETS_BUCKET,
            storage_path: storagePath,
            storage_public_url: publicUrlData.publicUrl,
            upload_url: '',
            drive_folder_id: '',
            target_folder_id: '',
            drive_backup_error: null,
            file_name: fileName,
            asset_type: assetType,
            scene_number: sceneNumber,
        })
    } catch (error: any) {
        return NextResponse.json({
            success: false,
            error: String(error?.message || 'asset_upload_init_failed'),
        }, { status: 500 })
    }
}
