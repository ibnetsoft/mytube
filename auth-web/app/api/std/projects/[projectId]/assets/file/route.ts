import { NextResponse } from 'next/server'
import { supabaseAdmin } from '@/lib/supabaseAdmin'
import { requireStdUser } from '@/lib/stdWeb'
import { assetStorageRef } from '@/lib/stdAssetStorage'
import { downloadGcsObject, downloadGcsObjectViaSignedUrl, isGcsConfiguredAsync } from '@/lib/gcsStorage'

export const dynamic = 'force-dynamic'
export const maxDuration = 300
const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i

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
            .select('id,project_id,asset_type,drive_file_id,file_name,mime_type,status,metadata,updated_at')
            .eq('id', assetId)
            .eq('project_id', project.id)
            .in('status', ['uploaded', 'assigned'])
            .maybeSingle()
        if (assetError) return NextResponse.json({ success: false, error: assetError.message }, { status: 500 })
        asset = assetRow
    } else {
        const { data: assetRow, error: assetError } = await supabaseAdmin
            .from('std_project_assets')
            .select('id,project_id,asset_type,drive_file_id,file_name,mime_type,status,metadata,updated_at')
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

    const etag = `"${asset.id}-${String(asset.updated_at || '').replace(/[^0-9]/g, '')}"`
    const requestedRange = req.headers.get('range')
    if (!requestedRange && req.headers.get('if-none-match') === etag) {
        return new NextResponse(null, {
            status: 304,
            headers: { ETag: etag, 'Cache-Control': 'private, max-age=86400' },
        })
    }

    const storage = assetStorageRef(asset.metadata)
    const gcsBucket = storage.bucket
    const gcsPath = storage.path
    let fileBuffer: Buffer | null = null
    let source = storage.provider
    let responseStatus = 200
    let contentRange: string | null = null
    let upstreamContentLength: string | null = null
    let upstreamContentType: string | null = null

    if (!gcsPath) {
        return NextResponse.json({ success: false, error: 'Asset does not have a storage path' }, { status: 404 })
    }
    if (storage.provider === 'gcs' && !(await isGcsConfiguredAsync())) {
        return NextResponse.json({ success: false, error: 'GCS storage is not configured' }, { status: 500 })
    }
    try {
        if (storage.provider === 'supabase') {
            const { data, error } = await supabaseAdmin.storage.from(storage.bucket).createSignedUrl(storage.path, 120)
            if (error || !data?.signedUrl) throw new Error(error?.message || 'Storage URL unavailable')
            const upstream = await fetch(data.signedUrl, {
                headers: requestedRange ? { Range: requestedRange } : {}, cache: 'no-store',
            })
            if (upstream.status === 416) return new NextResponse(null, { status: 416,
                headers: { 'Content-Range': upstream.headers.get('content-range') || 'bytes */*' } })
            if (!upstream.ok) throw new Error(`Storage HTTP ${upstream.status}`)
            return new NextResponse(upstream.body, {
                status: upstream.status,
                headers: {
                    'Content-Type': upstream.headers.get('content-type') || asset.mime_type || 'application/octet-stream',
                    'Cache-Control': 'private, max-age=86400', ETag: etag, 'Accept-Ranges': 'bytes',
                    'Vary': 'Authorization, Cookie, x-impersonate-email', 'X-STD-Media-Source': 'supabase',
                    ...(upstream.headers.get('content-length') ? { 'Content-Length': upstream.headers.get('content-length')! } : {}),
                    ...(upstream.headers.get('content-range') ? { 'Content-Range': upstream.headers.get('content-range')! } : {}),
                },
            })
        } else if (requestedRange && (/^(audio|video)\//.test(asset.mime_type || '') || ['video', 'audio'].includes(String(asset.asset_type || '').toLowerCase()))) {
            const chunk = await downloadGcsObjectViaSignedUrl({
                bucket: gcsBucket,
                objectPath: gcsPath,
                range: requestedRange,
            })
            fileBuffer = chunk.buffer
            responseStatus = chunk.status === 206 ? 206 : 200
            contentRange = chunk.contentRange
            upstreamContentLength = chunk.contentLength
            upstreamContentType = chunk.contentType
        } else {
            fileBuffer = await downloadGcsObject({ bucket: gcsBucket, objectPath: gcsPath })
        }
    } catch (error: any) {
        console.warn('[STD Asset File] storage download failed:', storage.provider, error?.message)
        if (isMediaRestoreRequest) {
            return new NextResponse(null, { status: 204, headers: { 'Cache-Control': 'no-store' } })
        }
        return NextResponse.json({
            success: false,
            error: 'Asset file could not be loaded from storage',
            detail: error?.message || 'gcs_download_failed',
        }, { status: 404 })
    }

    return new NextResponse(new Uint8Array(fileBuffer), {
        status: responseStatus,
        headers: {
            'Content-Type': upstreamContentType || asset?.mime_type || 'application/octet-stream',
            'Content-Length': upstreamContentLength || String(fileBuffer.length),
            'Cache-Control': 'private, max-age=86400',
            ETag: etag,
            'Accept-Ranges': 'bytes',
            ...(contentRange ? { 'Content-Range': contentRange } : {}),
            'Vary': 'Authorization, Cookie, x-impersonate-email',
            'Content-Disposition': `inline; filename="${encodeURIComponent(asset?.file_name || 'std_asset')}"`,
            'X-STD-Media-Source': source,
        },
    })
}
