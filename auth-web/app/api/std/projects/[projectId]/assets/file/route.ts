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
    const gcsBucket = String(asset.metadata?.gcs_bucket || (asset.metadata?.storage_provider === 'gcs' ? asset.metadata?.storage_bucket : '') || '')
    const gcsPath = String(asset.metadata?.gcs_path || asset.metadata?.storage_path || storage.path).replace(/^\/+/, '')
    let fileBuffer: Buffer | null = null
    let source = 'supabase'
    let responseStatus = 200
    let contentRange: string | null = null
    let upstreamContentLength: string | null = null
    let upstreamContentType: string | null = null

    if (!gcsPath) {
        return NextResponse.json({ success: false, error: 'Asset does not have a storage path' }, { status: 404 })
    }
    try {
        if (asset.metadata?.storage_provider !== 'gcs') {
            // Server-authenticated stream avoids expiring intermediate signed URLs.
            // Project/asset ownership has already been checked above.
            const objectPath = [storage.bucket, ...storage.path.split('/')].map(encodeURIComponent).join('/')
            const upstream = await fetch(`${process.env.NEXT_PUBLIC_SUPABASE_URL}/storage/v1/object/authenticated/${objectPath}`, {
                headers: {
                    apikey: process.env.SUPABASE_SERVICE_ROLE_KEY!,
                    Authorization: `Bearer ${process.env.SUPABASE_SERVICE_ROLE_KEY!}`,
                    ...(requestedRange ? { Range: requestedRange } : {}),
                }, cache: 'no-store',
            })
            if (upstream.status === 416) return new NextResponse(null, { status: 416,
                headers: upstream.headers.has('content-range') ? { 'Content-Range': upstream.headers.get('content-range')! } : {} })
            if (!upstream.ok) {
                const failure = await upstream.json().catch(() => ({}))
                const missing = upstream.status === 404 || failure.code === 'NoSuchKey'
                    || failure.error === 'not_found' || /^(?:Object not found|The resource was not found)$/i.test(failure.message || '')
                if (!missing) return NextResponse.json({ success: false, error: `Supabase storage HTTP ${upstream.status}` }, { status: 502 })
            }
                if (upstream.ok) {
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
                }
                if (!upstream.bodyUsed) await upstream.body?.cancel()
        }
        source = 'gcs'
        if (!(await isGcsConfiguredAsync())) return NextResponse.json({ success: false, error: 'GCS storage is not configured' }, { status: 503 })
        if (requestedRange && (/^(audio|video)\//.test(asset.mime_type || '') || ['video', 'audio'].includes(String(asset.asset_type || '').toLowerCase()))) {
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
        console.warn('[STD Asset File] storage download failed:', source, error?.message)
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
