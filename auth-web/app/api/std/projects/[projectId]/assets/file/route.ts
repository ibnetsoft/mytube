import { NextResponse } from 'next/server'
import { supabaseAdmin } from '@/lib/supabaseAdmin'
import { requireStdUser } from '@/lib/stdWeb'
import { downloadStdDriveFile } from '@/lib/stdGoogleDrive'

export const dynamic = 'force-dynamic'
export const maxDuration = 300
const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i
const CONTENT_ASSETS_BUCKET = 'content-assets'

function topicIdFromProjectParam(projectId: string): number | null {
    const value = String(projectId || '').trim()
    const match = value.match(/^(?:proj-)?(\d+)$/i)
    if (match) return Number(match[1])
    return null
}

async function loadStdProject(projectId: string, employeeEmail: string) {
    const topicQueueId = topicIdFromProjectParam(projectId)

    let query = supabaseAdmin.from('std_projects').select('id')
    if (UUID_RE.test(projectId)) {
        query = query.eq('id', projectId)
    } else if (topicQueueId != null && Number.isFinite(topicQueueId)) {
        query = query.eq('topic_queue_id', topicQueueId)
    } else {
        return { data: null, error: null }
    }

    if (!employeeEmail) return { data: null, error: null }
    query = query.eq('employee_email', employeeEmail)

    return await query.maybeSingle()
}

export async function GET(req: Request, { params }: { params: { projectId: string } }) {
    const auth = await requireStdUser(req)
    if (!auth.ok) return auth.response

    const url = new URL(req.url)
    const isMediaRestoreRequest = req.headers.get('x-std-media-restore') === '1'
    const assetId = String(url.searchParams.get('assetId') || '').trim()
    const driveFileId = String(url.searchParams.get('driveFileId') || '').trim()
    if (!assetId && !driveFileId) {
        return NextResponse.json({ success: false, error: 'assetId or driveFileId is required' }, { status: 400 })
    }

    const { data: project, error: projectError } = await loadStdProject(params.projectId, auth.requester.email)
    if (projectError) return NextResponse.json({ success: false, error: (projectError as any)?.message || 'Project query failed' }, { status: 500 })
    if (!project) return NextResponse.json({ success: false, error: 'Project not found' }, { status: 404 })

    let asset: any = null
    if (assetId) {
        const { data: assetRow, error: assetError } = await supabaseAdmin
            .from('std_project_assets')
            .select('id,project_id,asset_type,drive_file_id,file_name,mime_type,status,metadata')
            .eq('id', assetId)
            .eq('project_id', project.id)
            .in('status', ['uploaded', 'assigned'])
            .maybeSingle()
        if (assetError) return NextResponse.json({ success: false, error: assetError.message }, { status: 500 })
        asset = assetRow
    } else {
        const { data: assetRow, error: assetError } = await supabaseAdmin
            .from('std_project_assets')
            .select('id,project_id,asset_type,drive_file_id,file_name,mime_type,status,metadata')
            .eq('project_id', project.id)
            .eq('drive_file_id', driveFileId)
            .in('status', ['uploaded', 'assigned'])
            .limit(1)
            .maybeSingle()
        if (assetError) return NextResponse.json({ success: false, error: assetError.message }, { status: 500 })
        asset = assetRow
    }
    // Never fall back to an unverified request file ID, including invalid assetId + driveFileId pairs.
    if (!asset) return NextResponse.json({ success: false, error: 'Asset not found' }, { status: 404 })

    const storageBucket = String(asset?.metadata?.storage_bucket || CONTENT_ASSETS_BUCKET).trim() || CONTENT_ASSETS_BUCKET
    const storagePath = String(asset?.metadata?.storage_path || '').trim().replace(/^\/+/, '')
    let fileBuffer: Buffer | null = null
    let source = ''

    if (storagePath) {
        const { data, error } = await supabaseAdmin.storage.from(storageBucket).download(storagePath)
        if (data && !error) {
            fileBuffer = Buffer.from(await data.arrayBuffer())
            source = 'storage'
        } else {
            console.warn('[STD Asset File] Storage download failed; trying Drive:', error?.message || 'storage_asset_missing')
        }
    }

    if (!fileBuffer) {
        const targetDriveFileId = asset.drive_file_id
        if (!targetDriveFileId) return NextResponse.json({ success: false, error: 'Asset not found' }, { status: 404 })
        try {
            fileBuffer = await downloadStdDriveFile(targetDriveFileId)
            source = 'drive'
        } catch (error: any) {
            console.warn('[STD Asset File] Drive download failed:', error?.message)
            if (isMediaRestoreRequest) {
                return new NextResponse(null, { status: 204, headers: { 'Cache-Control': 'no-store' } })
            }
            return NextResponse.json({
                success: false,
                error: 'Asset file could not be loaded from Storage or Drive',
                detail: error?.message || 'drive_download_failed',
            }, { status: 404 })
        }
    }

    return new NextResponse(new Uint8Array(fileBuffer), {
        headers: {
            'Content-Type': asset?.mime_type || 'application/octet-stream',
            'Content-Length': String(fileBuffer.length),
            'Cache-Control': 'private, no-store',
            'Vary': 'Authorization, Cookie, x-impersonate-email',
            'Content-Disposition': `inline; filename="${encodeURIComponent(asset?.file_name || 'std_asset')}"`,
            'X-STD-Media-Source': source,
        },
    })
}
