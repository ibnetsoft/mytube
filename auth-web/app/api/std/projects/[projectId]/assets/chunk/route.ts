import { NextResponse } from 'next/server'
import { supabaseAdmin } from '@/lib/supabaseAdmin'
import { requireStdUser } from '@/lib/stdWeb'

export const dynamic = 'force-dynamic'
export const maxDuration = 300

const DRIVE_UPLOAD_HOST = 'www.googleapis.com'
const DRIVE_UPLOAD_PATH = '/upload/drive/v3/files'

function isAllowedDriveUploadUrl(value: string): boolean {
    try {
        const url = new URL(value)
        return url.protocol === 'https:'
            && url.hostname === DRIVE_UPLOAD_HOST
            && url.pathname === DRIVE_UPLOAD_PATH
            && url.searchParams.get('uploadType') === 'resumable'
    } catch {
        return false
    }
}

export async function POST(req: Request, { params }: { params: { projectId: string } }) {
    const auth = await requireStdUser(req)
    if (!auth.ok) return auth.response

    const url = new URL(req.url)
    const uploadUrl = String(url.searchParams.get('upload_url') || '').trim()
    const contentRange = String(req.headers.get('content-range') || '').trim()
    const contentType = String(req.headers.get('content-type') || 'application/octet-stream').trim()

    if (!isAllowedDriveUploadUrl(uploadUrl)) {
        return NextResponse.json({ success: false, error: 'Invalid Drive upload URL' }, { status: 400 })
    }
    if (!contentRange || !/^bytes \d+-\d+\/\d+$/i.test(contentRange)) {
        return NextResponse.json({ success: false, error: 'Invalid upload content range' }, { status: 400 })
    }

    const { data: project, error: projectError } = await supabaseAdmin
        .from('std_projects')
        .select('id,status')
        .eq('id', params.projectId)
        .eq('employee_email', auth.requester.email)
        .maybeSingle()

    if (projectError) return NextResponse.json({ success: false, error: projectError.message }, { status: 500 })
    if (!project) return NextResponse.json({ success: false, error: 'Project not found' }, { status: 404 })
    if (['review_requested', 'approved', 'canceled'].includes(project.status)) {
        return NextResponse.json({ success: false, error: 'Project is not editable' }, { status: 409 })
    }

    try {
        const chunk = Buffer.from(await req.arrayBuffer())
        if (!chunk.length) {
            return NextResponse.json({ success: false, error: 'Upload chunk is empty' }, { status: 400 })
        }

        const driveRes = await fetch(uploadUrl, {
            method: 'PUT',
            headers: {
                'Content-Type': contentType,
                'Content-Length': String(chunk.length),
                'Content-Range': contentRange,
            },
            body: chunk,
        })

        const text = await driveRes.text()
        if (driveRes.status === 308) {
            return NextResponse.json({
                success: true,
                complete: false,
                range: driveRes.headers.get('range') || null,
            })
        }

        if (!driveRes.ok) {
            return NextResponse.json({
                success: false,
                error: `Drive chunk upload failed: HTTP ${driveRes.status} ${text.slice(0, 300)}`,
            }, { status: 502 })
        }

        let driveFile: any = {}
        try {
            driveFile = text ? JSON.parse(text) : {}
        } catch {
            return NextResponse.json({ success: false, error: 'Drive upload completed without JSON metadata' }, { status: 502 })
        }

        return NextResponse.json({
            success: true,
            complete: true,
            drive_file: driveFile,
        })
    } catch (error: any) {
        return NextResponse.json({
            success: false,
            error: error?.message || 'Chunk upload failed',
        }, { status: 500 })
    }
}
