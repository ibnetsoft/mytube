import { NextResponse } from 'next/server'
import { downloadGcsObject, downloadGcsObjectViaSignedUrl, isGcsConfiguredAsync } from '@/lib/gcsStorage'
import { requireStdUser } from '@/lib/stdWeb'

export const dynamic = 'force-dynamic'
export const maxDuration = 300

function contentTypeForPath(path: string) {
    const lower = path.toLowerCase()
    if (lower.endsWith('.png')) return 'image/png'
    if (lower.endsWith('.jpg') || lower.endsWith('.jpeg')) return 'image/jpeg'
    if (lower.endsWith('.webp')) return 'image/webp'
    if (lower.endsWith('.mp4')) return 'video/mp4'
    if (lower.endsWith('.mp3')) return 'audio/mpeg'
    if (lower.endsWith('.wav')) return 'audio/wav'
    return 'application/octet-stream'
}

export async function GET(req: Request) {
    const auth = await requireStdUser(req)
    if (!auth.ok) return auth.response

    const url = new URL(req.url)
    const bucket = String(url.searchParams.get('bucket') || '').trim()
    const objectPath = String(url.searchParams.get('path') || '').trim().replace(/^\/+/, '')
    if (!objectPath || objectPath.includes('..')) {
        return NextResponse.json({ success: false, error: 'Invalid GCS object path' }, { status: 400 })
    }
    if (!(await isGcsConfiguredAsync())) {
        return NextResponse.json({ success: false, error: 'GCS storage is not configured' }, { status: 500 })
    }

    try {
        const range = req.headers.get('range')
        let buffer: Buffer
        let status = 200
        let contentRange: string | null = null
        let contentLength: string | null = null
        let upstreamType: string | null = null
        if (range) {
            const chunk = await downloadGcsObjectViaSignedUrl({ bucket, objectPath, range })
            buffer = chunk.buffer
            status = chunk.status === 206 ? 206 : 200
            contentRange = chunk.contentRange
            contentLength = chunk.contentLength
            upstreamType = chunk.contentType
        } else {
            buffer = await downloadGcsObject({ bucket, objectPath })
        }
        return new NextResponse(new Uint8Array(buffer), {
            status,
            headers: {
                'Content-Type': upstreamType || contentTypeForPath(objectPath),
                'Content-Length': contentLength || String(buffer.length),
                'Cache-Control': 'private, max-age=86400',
                'Accept-Ranges': 'bytes',
                ...(contentRange ? { 'Content-Range': contentRange } : {}),
                'Vary': 'Authorization, Cookie, x-impersonate-email',
            },
        })
    } catch (error: any) {
        return NextResponse.json({
            success: false,
            error: 'GCS file could not be loaded',
            detail: error?.message || 'gcs_download_failed',
        }, { status: 404 })
    }
}
