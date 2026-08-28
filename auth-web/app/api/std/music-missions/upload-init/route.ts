import { NextResponse } from 'next/server'
import { supabaseAdmin } from '@/lib/supabaseAdmin'
import { requireStdUser } from '@/lib/stdWeb'
import {
    createStdDriveUploadSession,
    ensureDriveFolder,
    resolveDriveRootFolderId,
    sanitizeDriveName,
} from '@/lib/stdGoogleDrive'

export const dynamic = 'force-dynamic'

function validAudioMime(mimeType: string): boolean {
    return mimeType.startsWith('audio/') || mimeType === 'application/octet-stream'
}

export async function POST(req: Request) {
    const auth = await requireStdUser(req)
    if (!auth.ok) return auth.response

    let body: any
    try {
        body = await req.json()
    } catch {
        return NextResponse.json({ success: false, error: 'Invalid JSON' }, { status: 400 })
    }

    const taskId = String(body?.task_id || '').trim()
    const mimeType = String(body?.mime_type || 'audio/mpeg').trim()
    const fileName = sanitizeDriveName(String(body?.file_name || ''), 'music_submission.mp3')
    const fileSize = Number(body?.file_size || 0) || null

    if (!taskId) return NextResponse.json({ success: false, error: 'task_id is required' }, { status: 400 })
    if (!validAudioMime(mimeType)) return NextResponse.json({ success: false, error: 'Audio file is required' }, { status: 400 })

    const { data: task, error: taskError } = await supabaseAdmin
        .from('music_prompt_tasks')
        .select('id,title,status')
        .eq('id', taskId)
        .maybeSingle()

    if (taskError) return NextResponse.json({ success: false, error: taskError.message }, { status: 500 })
    if (!task || task.status !== 'open') return NextResponse.json({ success: false, error: 'Music mission is not open' }, { status: 404 })

    try {
        const rootFolderId = await resolveDriveRootFolderId()
        if (!rootFolderId) throw new Error('drive_root_folder_not_configured')
        const root = await ensureDriveFolder(rootFolderId, 'STD_music_submissions')
        const missionFolder = await ensureDriveFolder(root, sanitizeDriveName(`${task.id}_${task.title}`, 'music_mission'))
        const userFolder = await ensureDriveFolder(missionFolder, sanitizeDriveName(auth.requester.email, 'worker'))
        const uploadUrl = await createStdDriveUploadSession({
            folderId: userFolder,
            fileName,
            mimeType,
            fileSize,
        })

        return NextResponse.json({
            success: true,
            upload_url: uploadUrl,
            target_folder_id: userFolder,
            file_name: fileName,
        })
    } catch (error: any) {
        return NextResponse.json({ success: false, error: error?.message || 'Music upload init failed' }, { status: 500 })
    }
}
