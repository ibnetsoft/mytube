import { createClient } from '@supabase/supabase-js'
import { NextResponse } from 'next/server'

export const dynamic = 'force-dynamic'

const getAdmin = () => createClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.SUPABASE_SERVICE_ROLE_KEY!,
    { auth: { persistSession: false } }
)

function buildDriveOpenLink(fileId?: string | null) {
    if (!fileId) return null
    return `https://drive.google.com/file/d/${fileId}/view`
}

function buildDriveFolderLink(folderId?: string | null) {
    if (!folderId) return null
    return `https://drive.google.com/drive/folders/${folderId}`
}

function buildDriveThumbnailPreview(fileId?: string | null) {
    if (!fileId) return null
    return `https://drive.google.com/thumbnail?id=${fileId}&sz=w512`
}

function normalizePublishingRequest(request: any) {
    const metadata = request?.metadata || {}
    const title =
        metadata.title ||
        metadata.project_name ||
        metadata.topic ||
        'Untitled Video'

    const driveFolderId = metadata.drive_folder_id || metadata.result_folder_id || null
    const driveVideoFileId = metadata.drive_video_file_id || metadata.result_video_file_id || null
    const driveThumbnailFileId = metadata.drive_thumbnail_file_id || metadata.result_thumbnail_file_id || null
    const driveMetadataFileId = metadata.drive_metadata_file_id || metadata.result_metadata_file_id || null
    const projectId = metadata.project_id || null
    const publishError = metadata.publish_error || null

    return {
        ...request,
        metadata: {
            ...metadata,
            project_id: projectId,
            title,
            drive_folder_id: driveFolderId,
            drive_video_file_id: driveVideoFileId,
            drive_thumbnail_file_id: driveThumbnailFileId,
            drive_metadata_file_id: driveMetadataFileId,
            drive_folder_link: buildDriveFolderLink(driveFolderId),
            drive_video_link: buildDriveOpenLink(driveVideoFileId),
            drive_thumbnail_link: buildDriveOpenLink(driveThumbnailFileId),
            drive_metadata_link: buildDriveOpenLink(driveMetadataFileId),
            drive_thumbnail_preview_url:
                metadata.thumbnail_preview_url ||
                buildDriveThumbnailPreview(driveThumbnailFileId),
            youtube_url: metadata.videoId ? `https://youtu.be/${metadata.videoId}` : null,
            has_drive_bundle: Boolean(driveFolderId || driveVideoFileId || driveMetadataFileId),
            publish_error: publishError,
            published_at: metadata.published_at || null,
            failed_at: metadata.failed_at || null,
            is_invalid_request: !projectId,
        },
    }
}

export async function GET(req: Request) {
    try {
        const supabase = getAdmin()
        const { searchParams } = new URL(req.url)
        const userId = searchParams.get('userId')

        // join이 실패할 수 있으므로 간단하게 조회 후 필터링하거나, 관계가 확실할때만 사용
        // 여기서는 안전을 위해 단순 조회를 먼저 시도합니다.
        let query = supabase
            .from('publishing_requests')
            .select('*')
            .order('created_at', { ascending: false })

        if (userId) {
            query = query.eq('user_id', userId)
        }

        const { data: requests, error } = await query
        if (error) throw error

        // 수동으로 이메일 매핑 (선택 사항 - UI에서 유저 리스트와 매칭 가능하므로 일단 단순 반환)
        const normalized = (requests || []).map(normalizePublishingRequest)
        return NextResponse.json({ requests: normalized })
    } catch (error: any) {
        console.error("Publishing API Error:", error)
        return NextResponse.json({ error: error.message }, { status: 500 })
    }
}

export async function PATCH(req: Request) {
    try {
        const { requestId, status } = await req.json()
        if (!requestId || !status) return NextResponse.json({ error: 'Missing parameters' }, { status: 400 })

        const supabase = getAdmin()
        const { data: existing, error: existingError } = await supabase
            .from('publishing_requests')
            .select('id, metadata')
            .eq('id', requestId)
            .single()

        if (existingError) throw existingError
        if (status === 'to_be_published' && !existing?.metadata?.project_id) {
            return NextResponse.json({ error: 'Missing project_id in publishing request metadata' }, { status: 400 })
        }

        const { data, error } = await supabase
            .from('publishing_requests')
            .update({ status })
            .eq('id', requestId)
            .select()

        if (error) throw error
        return NextResponse.json({ success: true, data: data[0] })
    } catch (error: any) {
        return NextResponse.json({ error: error.message }, { status: 500 })
    }
}
