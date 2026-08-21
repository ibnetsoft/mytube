import { NextResponse } from 'next/server'
import { supabaseAdmin } from '@/lib/supabaseAdmin'
import { requireStdUser } from '@/lib/stdWeb'
import { downloadStdDriveFile } from '@/lib/stdGoogleDrive'

export const dynamic = 'force-dynamic'
export const maxDuration = 300

export async function GET(req: Request, { params }: { params: { projectId: string } }) {
    const auth = await requireStdUser(req)
    if (!auth.ok) return auth.response

    const url = new URL(req.url)
    const assetId = String(url.searchParams.get('assetId') || '').trim()
    if (!assetId) {
        return NextResponse.json({ success: false, error: 'assetId is required' }, { status: 400 })
    }

    const { data: project, error: projectError } = await supabaseAdmin
        .from('std_projects')
        .select('id')
        .eq('id', params.projectId)
        .eq('employee_email', auth.requester.email)
        .maybeSingle()

    if (projectError) return NextResponse.json({ success: false, error: projectError.message }, { status: 500 })
    if (!project) return NextResponse.json({ success: false, error: 'Project not found' }, { status: 404 })

    const { data: asset, error: assetError } = await supabaseAdmin
        .from('std_project_assets')
        .select('drive_file_id,file_name,mime_type')
        .eq('id', assetId)
        .eq('project_id', project.id)
        .eq('asset_type', 'audio')
        .maybeSingle()

    if (assetError) return NextResponse.json({ success: false, error: assetError.message }, { status: 500 })
    if (!asset?.drive_file_id) return NextResponse.json({ success: false, error: 'TTS audio not found' }, { status: 404 })

    const audioBuffer = await downloadStdDriveFile(asset.drive_file_id)
    return new NextResponse(new Uint8Array(audioBuffer), {
        headers: {
            'Content-Type': asset.mime_type || 'audio/mpeg',
            'Content-Length': String(audioBuffer.length),
            'Cache-Control': 'private, max-age=300',
            'Content-Disposition': `inline; filename="${encodeURIComponent(asset.file_name || 'std_elevenlabs_tts.mp3')}"`,
        },
    })
}
