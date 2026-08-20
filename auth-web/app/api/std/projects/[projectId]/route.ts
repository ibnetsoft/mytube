import { NextResponse } from 'next/server'
import { supabaseAdmin } from '@/lib/supabaseAdmin'
import { requireStdUser } from '@/lib/stdWeb'

export const dynamic = 'force-dynamic'

export async function GET(req: Request, { params }: { params: { projectId: string } }) {
    const auth = await requireStdUser(req)
    if (!auth.ok) return auth.response

    let query = supabaseAdmin.from('std_projects').select('*').eq('id', params.projectId)
    if (auth.requester.email && !auth.requester.email.startsWith('admin') && !auth.requester.email.startsWith('worker')) {
        query = query.eq('employee_email', auth.requester.email)
    }
    const { data: project, error } = await query.maybeSingle()

    if (error) return NextResponse.json({ success: false, error: error.message }, { status: 500 })
    if (!project) return NextResponse.json({ success: false, error: 'Project not found' }, { status: 404 })

    const [{ data: scenes, error: scenesError }, { data: assets, error: assetsError }] = await Promise.all([
        supabaseAdmin
            .from('std_project_scenes')
            .select('id,project_id,scene_number,scene_title,scene_text,image_prompt,video_prompt,asset_status,metadata,created_at,updated_at')
            .eq('project_id', project.id)
            .order('scene_number', { ascending: true }),
        supabaseAdmin
            .from('std_project_assets')
            .select('id,project_id,scene_id,scene_number,asset_type,drive_file_id,drive_folder_id,file_name,mime_type,file_size,status,metadata,created_at,updated_at')
            .eq('project_id', project.id)
            .in('status', ['uploaded', 'assigned'])
            .order('created_at', { ascending: false }),
    ])

    if (scenesError) return NextResponse.json({ success: false, error: scenesError.message }, { status: 500 })
    if (assetsError) return NextResponse.json({ success: false, error: assetsError.message }, { status: 500 })

    return NextResponse.json({ success: true, project, scenes: scenes || [], assets: assets || [] })
}

export async function PATCH(req: Request, { params }: { params: { projectId: string } }) {
    const auth = await requireStdUser(req)
    if (!auth.ok) return auth.response

    let body: any
    try {
        body = await req.json()
    } catch {
        return NextResponse.json({ success: false, error: 'Invalid JSON' }, { status: 400 })
    }

    const { data: project, error: projectError } = await supabaseAdmin
        .from('std_projects')
        .select('*')
        .eq('id', params.projectId)
        .eq('employee_email', auth.requester.email)
        .maybeSingle()

    if (projectError) return NextResponse.json({ success: false, error: projectError.message }, { status: 500 })
    if (!project) return NextResponse.json({ success: false, error: 'Project not found' }, { status: 404 })
    if (['review_requested', 'approved', 'canceled'].includes(project.status)) {
        return NextResponse.json({ success: false, error: 'Project is not editable' }, { status: 409 })
    }

    const incomingProgress = body?.progress_payload || {}
    const allowedProgressKeys = new Set(['thumbnail_completed', 'thumbnail_url', 'thumbnail_confirmed_at'])
    const progressPatch = Object.fromEntries(
        Object.entries(incomingProgress).filter(([key]) => allowedProgressKeys.has(key))
    )

    if (Object.keys(progressPatch).length === 0) {
        return NextResponse.json({ success: false, error: 'No supported fields to update' }, { status: 400 })
    }

    const { data: updated, error: updateError } = await supabaseAdmin
        .from('std_projects')
        .update({
            progress_payload: {
                ...(project.progress_payload || {}),
                ...progressPatch,
            },
            updated_at: new Date().toISOString(),
        })
        .eq('id', project.id)
        .select('*')
        .single()

    if (updateError) return NextResponse.json({ success: false, error: updateError.message }, { status: 500 })

    return NextResponse.json({ success: true, project: updated })
}
