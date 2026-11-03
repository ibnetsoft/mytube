import { assetContentIdentity } from '@/lib/stdContentIdentity'
import { randomUUID } from 'node:crypto'
import { isComicProject } from '@/lib/stdComic'
import { canEditStdAsset } from '@/lib/stdAssetEditPolicy'
import { NextResponse } from 'next/server'
import { supabaseAdmin } from '@/lib/supabaseAdmin'
import { requireStdUser } from '@/lib/stdWeb'
import { isStdRequiredClipScene, stdRequiredVideoSceneCount, strictRevisionSceneUploadAllowed } from '@/lib/stdPolicy'
import {
    buildStdGcsObjectPath,
    createGcsSignedUploadUrl,
    isGcsConfiguredAsync,
    sanitizeGcsObjectName,
} from '@/lib/gcsStorage'

export const dynamic = 'force-dynamic'

const ASSET_TYPES = new Set(['image', 'video', 'audio', 'bgm', 'sfx', 'thumbnail', 'original'])

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
    let stage = 'sign_upload'
    try {
        body = await req.json()
    } catch {
        return NextResponse.json({ success: false, error: 'Invalid JSON' }, { status: 400 })
    }

    const assetType = String(body?.asset_type || '').toLowerCase()
    const mimeType = String(body?.mime_type || '').trim()
    const fileName = sanitizeGcsObjectName(String(body?.file_name || ''), 'asset')
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

    if (sceneNumber != null && !strictRevisionSceneUploadAllowed(project, sceneNumber, assetType)) {
        return NextResponse.json({ success: false, error: 'Video is not selected for this scene.', code: 'video_not_selected' }, { status: 422 })
    }
    if (sceneNumber != null && project.project_payload?.strict_content_identity !== true && isStdRequiredClipScene(sceneNumber, project) && assetType === 'image') {
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
        && project.project_payload?.strict_content_identity !== true
        && sceneNumber > stdRequiredVideoSceneCount(project)
        && ['image', 'video'].includes(assetType)
    ) {
        return NextResponse.json({
            success: false,
            error: `Image scenes after scene ${stdRequiredVideoSceneCount(project)} are protected and cannot be replaced.`,
            code: 'generated_image_scene_protected',
        }, { status: 422 })
    }

    try {
        const storagePath = buildStdGcsObjectPath({
            projectId: project.id,
            sceneNumber,
            fileName,
        })

        if (!(await isGcsConfiguredAsync())) {
            throw new Error('GCS storage is not configured')
        }
        const signedUpload = await createGcsSignedUploadUrl({
            objectPath: storagePath,
            contentType: mimeType,
            expiresInMinutes: 30,
        })

        const plannedScene = sceneNumber == null ? null : (project.project_payload?.structure?.scenes || project.project_payload?.scenes || []).find((s: any, i: number) => Number(s.scene_number || s.scene_order || i + 1) === sceneNumber)
        const identity = assetContentIdentity(project, { type: assetType, scene: plannedScene ? { ...plannedScene, scene_number: sceneNumber } : undefined })
        stage = 'record_upload_claim'
        // A timeout can occur after Postgres commits. Reuse the same ID so a
        // retry cannot create two claims for the same storage path.
        const claimId = randomUUID()
        const claim = {
            id: claimId, project_id: project.id, asset_type: 'other', status: 'uploaded', file_name: fileName,
            metadata: { kind: 'asset_upload_claim', upload_path: storagePath, content_identity: identity },
        }
        let receipt: any
        for (let attempt = 0; attempt < 4; attempt++) {
            receipt = await supabaseAdmin.from('std_project_assets').upsert(claim, { onConflict: 'id' }).select('id').single()
            if (!receipt.error) break
            const status = Number(receipt.status ?? receipt.error?.status ?? receipt.error?.code)
            const transient = status === 0 || status === 408 || status === 429 || status >= 500 || receipt.error?.retryable === true
            if (!transient || attempt === 3) throw receipt.error
            await new Promise(resolve => setTimeout(resolve, [1000, 3000, 8000][attempt]))
        }
        return NextResponse.json({
            success: true,
            content_identity: identity,
            upload_claim_id: receipt.data.id,
            storage_provider: 'gcs',
            secondary_storage_provider: null,
            storage_upload_url: signedUpload.signedUrl,
            storage_bucket: signedUpload.bucket,
            storage_path: storagePath,
            storage_public_url: '',
            upload_url: '',
            drive_folder_id: '',
            target_folder_id: '',
            drive_backup_error: null,
            file_name: fileName,
            asset_type: assetType,
            scene_number: sceneNumber,
        })
    } catch (error: any) {
        console.error('[STD asset upload init]', { stage, projectId: project.id, assetType,
            code: error?.code || error?.status || error?.error_code || null,
            message: String(error?.message || error?.title || 'unknown error').slice(0, 300) })
        return NextResponse.json({
            success: false,
            error: stage === 'record_upload_claim'
                ? '업로드 준비 중 저장소 연결이 불안정합니다. 편집 내용은 유지되어 있으니 잠시 후 다시 저장해 주세요.'
                : '이미지 업로드를 준비하지 못했습니다. 편집 내용은 유지되어 있으니 잠시 후 다시 저장해 주세요.',
        }, { status: 500 })
    }
}
