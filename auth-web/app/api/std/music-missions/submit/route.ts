import { NextResponse } from 'next/server'
import { supabaseAdmin } from '@/lib/supabaseAdmin'
import { requireStdUser } from '@/lib/stdWeb'
import { driveFileLink, getStdDriveFileMetadata } from '@/lib/stdGoogleDrive'
import { syncMusicLearningToNotion } from '@/lib/notionLearningSync'

export const dynamic = 'force-dynamic'

function cleanText(value: any, maxLength: number): string {
    return String(value || '').trim().slice(0, maxLength)
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

    const taskId = cleanText(body?.task_id, 80)
    const driveFileId = cleanText(body?.drive_file_id, 200)
    const targetFolderId = cleanText(body?.target_folder_id, 200)
    const toolName = cleanText(body?.tool_name, 120)
    const promptUsed = cleanText(body?.prompt_used, 12000)
    const lyrics = cleanText(body?.lyrics, 20000)
    const licenseConfirmed = Boolean(body?.license_confirmed)
    const originalityConfirmed = Boolean(body?.originality_confirmed)
    const commercialUseConfirmed = Boolean(body?.commercial_use_confirmed)

    if (!taskId) return NextResponse.json({ success: false, error: 'task_id is required' }, { status: 400 })
    if (!driveFileId) return NextResponse.json({ success: false, error: 'drive_file_id is required' }, { status: 400 })
    if (!toolName) return NextResponse.json({ success: false, error: 'Generation tool name is required' }, { status: 400 })
    if (!promptUsed) return NextResponse.json({ success: false, error: 'Prompt used is required' }, { status: 400 })
    if (!licenseConfirmed || !originalityConfirmed || !commercialUseConfirmed) {
        return NextResponse.json({ success: false, error: 'All license confirmations are required' }, { status: 400 })
    }

    const { data: task, error: taskError } = await supabaseAdmin
        .from('music_prompt_tasks')
        .select('id,title,status,reward_usdt,target_market,genre,mood,prompt,negative_rules,metadata')
        .eq('id', taskId)
        .maybeSingle()

    if (taskError) return NextResponse.json({ success: false, error: taskError.message }, { status: 500 })
    if (!task || task.status !== 'open') return NextResponse.json({ success: false, error: 'Music mission is not open' }, { status: 404 })

    try {
        const metadata = await getStdDriveFileMetadata(driveFileId)
        if (targetFolderId && Array.isArray(metadata.parents) && !metadata.parents.includes(targetFolderId)) {
            return NextResponse.json({ success: false, error: 'Drive file is not in the expected folder' }, { status: 400 })
        }
        const mimeType = String(metadata.mimeType || body?.mime_type || '')
        if (mimeType && !mimeType.startsWith('audio/') && mimeType !== 'application/octet-stream') {
            return NextResponse.json({ success: false, error: 'Uploaded file is not audio' }, { status: 400 })
        }

        const { data: submission, error: submissionError } = await supabaseAdmin
            .from('music_submissions')
            .insert({
                task_id: task.id,
                submitted_by: auth.requester.user.id,
                submitted_email: auth.requester.email,
                drive_file_id: metadata.id,
                drive_folder_id: targetFolderId || metadata.parents?.[0] || null,
                file_name: metadata.name || body?.file_name || 'music_submission.mp3',
                mime_type: metadata.mimeType || body?.mime_type || null,
                file_size: metadata.size ? Number(metadata.size) : Number(body?.file_size || 0) || null,
                tool_name: toolName,
                prompt_used: promptUsed,
                lyrics,
                license_confirmed: licenseConfirmed,
                originality_confirmed: originalityConfirmed,
                commercial_use_confirmed: commercialUseConfirmed,
                reward_usdt: task.reward_usdt || 0,
                metadata: {
                    task_title: task.title,
                    drive_file_link: driveFileLink(metadata.id),
                    uploaded_by: auth.requester.email,
                },
            })
            .select('*')
            .single()

        if (submissionError) return NextResponse.json({ success: false, error: submissionError.message }, { status: 500 })
        await syncMusicLearningToNotion({
            source: 'music_submission',
            source_id: `music-submission:${submission.id}`,
            submission_id: submission.id,
            task_id: task.id,
            title: task.title,
            target_market: task.target_market,
            genre: task.genre,
            mood: task.mood,
            prompt: task.prompt,
            prompt_used: promptUsed,
            lyrics,
            tool_name: toolName,
            negative_rules: task.negative_rules,
            outcome_quality: 'submitted',
            created_at: submission.created_at || new Date().toISOString(),
            metadata: {
                ...(task.metadata || {}),
                task_title: task.title,
                submitted_email: auth.requester.email,
                drive_file_link: driveFileLink(metadata.id),
                file_name: metadata.name || body?.file_name || 'music_submission.mp3',
            },
        })
        return NextResponse.json({ success: true, submission })
    } catch (error: any) {
        return NextResponse.json({ success: false, error: error?.message || 'Music submission failed' }, { status: 500 })
    }
}
