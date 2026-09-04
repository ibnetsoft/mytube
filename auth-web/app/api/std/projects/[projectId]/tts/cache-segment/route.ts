import { createHash } from 'crypto'
import { NextResponse } from 'next/server'
import { supabaseAdmin } from '@/lib/supabaseAdmin'
import { requireStdUser } from '@/lib/stdWeb'
import {
    driveFileLink,
    ensureStdProjectDriveFolders,
    uploadStdDriveBuffer,
} from '@/lib/stdGoogleDrive'

export const dynamic = 'force-dynamic'
export const maxDuration = 120

const MAX_SEGMENT_AUDIO_BYTES = 2_500_000
const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i

function topicIdFromProjectParam(projectId: string) {
    const value = String(projectId || '').trim()
    const match = value.match(/^(?:proj-)?(\d+)$/i)
    return match ? Number(match[1]) : null
}

async function loadStdProject(projectId: string, employeeEmail: string) {
    const topicQueueId = topicIdFromProjectParam(projectId)
    let query = supabaseAdmin.from('std_projects').select('*')
    if (UUID_RE.test(projectId)) {
        query = query.eq('id', projectId)
    } else if (topicQueueId != null && Number.isFinite(topicQueueId)) {
        query = query.eq('topic_queue_id', topicQueueId)
    } else {
        return { data: null, error: null }
    }

    const ownedResult = await query.eq('employee_email', employeeEmail).maybeSingle()
    if (ownedResult.data || ownedResult.error) return ownedResult

    let fallbackQuery = supabaseAdmin.from('std_projects').select('*')
    if (UUID_RE.test(projectId)) {
        fallbackQuery = fallbackQuery.eq('id', projectId)
    } else {
        fallbackQuery = fallbackQuery.eq('topic_queue_id', topicQueueId)
    }
    return fallbackQuery.maybeSingle()
}

function safeCacheKey(value: FormDataEntryValue | null): string {
    return String(value || '').replace(/[^a-zA-Z0-9_-]/g, '').slice(0, 80)
}

export async function POST(req: Request, { params }: { params: { projectId: string } }) {
    const auth = await requireStdUser(req)
    if (!auth.ok) return auth.response

    let form: FormData
    try {
        form = await req.formData()
    } catch {
        return NextResponse.json({ success: false, error: 'Invalid segment cache form data' }, { status: 400 })
    }

    const fileValue = form.get('file')
    const cacheKey = safeCacheKey(form.get('cache_key'))
    if (!(fileValue instanceof File) || !fileValue.type.startsWith('audio/')) {
        return NextResponse.json({ success: false, error: 'Audio file is required' }, { status: 400 })
    }
    if (!cacheKey) {
        return NextResponse.json({ success: false, error: 'Segment cache key is required' }, { status: 400 })
    }
    if (fileValue.size <= 0 || fileValue.size > MAX_SEGMENT_AUDIO_BYTES) {
        return NextResponse.json({ success: false, error: 'Segment audio size is invalid' }, { status: 413 })
    }

    const { data: project, error: projectError } = await loadStdProject(
        params.projectId,
        auth.requester.email
    )
    if (projectError) return NextResponse.json({ success: false, error: projectError.message }, { status: 500 })
    if (!project) return NextResponse.json({ success: false, error: 'Project not found' }, { status: 404 })

    const { data: existingAsset, error: existingError } = await supabaseAdmin
        .from('std_project_assets')
        .select('*')
        .eq('project_id', project.id)
        .eq('asset_type', 'other')
        .in('status', ['uploaded', 'assigned'])
        .eq('metadata->>kind', 'vrew_segment_tts')
        .eq('metadata->>cache_key', cacheKey)
        .order('created_at', { ascending: false })
        .limit(1)
        .maybeSingle()
    if (existingError) return NextResponse.json({ success: false, error: existingError.message }, { status: 500 })
    if (existingAsset?.drive_file_id) {
        return NextResponse.json({ success: true, cached: true, asset: existingAsset })
    }

    try {
        const folders = await ensureStdProjectDriveFolders(project)
        const buffer = Buffer.from(await fileValue.arrayBuffer())
        const fileName = String(form.get('file_name') || fileValue.name || `vrew_segment_${cacheKey}.mp3`)
        const driveFile = await uploadStdDriveBuffer(
            folders.originalsFolderId,
            fileName,
            buffer,
            fileValue.type || 'audio/mpeg',
            `AIR STD Vrew segment cache for project ${project.id}`
        )
        const now = new Date().toISOString()

        await supabaseAdmin
            .from('std_project_assets')
            .update({ status: 'replaced', updated_at: now })
            .eq('project_id', project.id)
            .eq('asset_type', 'other')
            .eq('metadata->>kind', 'vrew_segment_tts')
            .eq('metadata->>cache_key', cacheKey)
            .in('status', ['uploaded', 'assigned'])

        const segmentIndex = Number(form.get('segment_index'))
        const text = String(form.get('text') || '').trim().slice(0, 10_000)
        const { data: asset, error: assetError } = await supabaseAdmin
            .from('std_project_assets')
            .insert({
                project_id: project.id,
                scene_id: null,
                scene_number: Number.isFinite(segmentIndex) ? segmentIndex + 1 : null,
                asset_type: 'other',
                drive_file_id: driveFile.id,
                drive_folder_id: folders.originalsFolderId,
                file_name: driveFile.name || fileName,
                mime_type: driveFile.mimeType || fileValue.type || 'audio/mpeg',
                file_size: driveFile.size ? Number(driveFile.size) : buffer.length,
                status: 'uploaded',
                uploaded_by: auth.requester.user.id,
                metadata: {
                    kind: 'vrew_segment_tts',
                    cache_key: cacheKey,
                    segment_index: Number.isFinite(segmentIndex) ? segmentIndex : null,
                    provider: String(form.get('provider') || ''),
                    voice_id: String(form.get('voice_id') || ''),
                    model_id: String(form.get('model_id') || ''),
                    tts_speed: Number(form.get('speed')) || 1,
                    stability: Number(form.get('stability')) || 0,
                    style: Number(form.get('style')) || 0,
                    text,
                    text_hash: createHash('sha1').update(text).digest('hex'),
                    generated_by: auth.requester.email,
                    web_view_link: driveFile.webViewLink || driveFileLink(driveFile.id),
                    upload_mode: 'fast_preview_background_cache',
                },
            })
            .select('*')
            .single()
        if (assetError) throw assetError

        await supabaseAdmin
            .from('std_projects')
            .update({
                drive_folder_id: folders.projectFolderId,
                updated_at: now,
            })
            .eq('id', project.id)

        return NextResponse.json({ success: true, cached: false, asset })
    } catch (error: any) {
        console.error('[STD Vrew SegmentCache] failed:', error?.message)
        return NextResponse.json({ success: false, error: error?.message || 'Segment cache upload failed' }, { status: 500 })
    }
}
