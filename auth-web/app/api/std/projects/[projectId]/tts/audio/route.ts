import { NextResponse } from 'next/server'
import { supabaseAdmin } from '@/lib/supabaseAdmin'
import { requireStdUser } from '@/lib/stdWeb'
import { downloadStdDriveFile } from '@/lib/stdGoogleDrive'

export const dynamic = 'force-dynamic'
export const maxDuration = 300
const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i

function topicIdFromProjectParam(projectId: string) {
    const value = String(projectId || '').trim()
    const legacyMatch = value.match(/^proj--?(\d+)$/i)
    if (legacyMatch) return Number(legacyMatch[1])

    const numeric = Number(value)
    if (Number.isFinite(numeric) && numeric >= 1_000_000_000) return numeric - 1_000_000_000
    return null
}

async function loadStdProject(projectId: string, employeeEmail: string) {
    let query = supabaseAdmin.from('std_projects').select('id').eq('employee_email', employeeEmail)
    const topicQueueId = topicIdFromProjectParam(projectId)

    if (UUID_RE.test(projectId)) {
        query = query.eq('id', projectId)
    } else if (topicQueueId != null && Number.isFinite(topicQueueId)) {
        query = query.eq('topic_queue_id', topicQueueId)
    } else {
        return { data: null, error: null }
    }

    return await query.maybeSingle()
}

export async function GET(req: Request, { params }: { params: { projectId: string } }) {
    const auth = await requireStdUser(req)
    if (!auth.ok) return auth.response

    const url = new URL(req.url)
    const assetId = String(url.searchParams.get('assetId') || '').trim()
    const driveFileId = String(url.searchParams.get('driveFileId') || '').trim()
    if (!assetId && !driveFileId) {
        return NextResponse.json({ success: false, error: 'assetId or driveFileId is required' }, { status: 400 })
    }

    const { data: project, error: projectError } = await loadStdProject(params.projectId, auth.requester.email)

    if (projectError) return NextResponse.json({ success: false, error: projectError.message }, { status: 500 })
    if (!project) return NextResponse.json({ success: false, error: 'Project not found' }, { status: 404 })

    let asset: any = null
    if (assetId) {
        const { data: assetRow, error: assetError } = await supabaseAdmin
            .from('std_project_assets')
            .select('drive_file_id,file_name,mime_type')
            .eq('id', assetId)
            .eq('project_id', project.id)
            .eq('asset_type', 'audio')
            .maybeSingle()

        if (assetError) return NextResponse.json({ success: false, error: assetError.message }, { status: 500 })
        asset = assetRow
    }

    const targetDriveFileId = asset?.drive_file_id || driveFileId
    if (!targetDriveFileId) return NextResponse.json({ success: false, error: 'TTS audio not found' }, { status: 404 })

    const audioBuffer = await downloadStdDriveFile(targetDriveFileId)
    return new NextResponse(new Uint8Array(audioBuffer), {
        headers: {
            'Content-Type': asset?.mime_type || 'audio/mpeg',
            'Content-Length': String(audioBuffer.length),
            'Cache-Control': 'private, max-age=300',
            'Content-Disposition': `inline; filename="${encodeURIComponent(asset?.file_name || 'std_tts.mp3')}"`,
        },
    })
}
