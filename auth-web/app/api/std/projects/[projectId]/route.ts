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
    const incomingProjectPayload = body?.project_payload || {}
    const incomingScenes = Array.isArray(incomingProjectPayload?.scenes) ? incomingProjectPayload.scenes : []
    const allowedProgressKeys = new Set([
        'thumbnail_completed',
        'thumbnail_url',
        'thumbnail_confirmed_at',
        'subtitles_saved',
        'subtitles_completed',
    ])
    const allowedProjectPayloadKeys = new Set(['script', 'subtitles', 'subtitles_saved', 'title', 'video_title', 'scenes', 'render_settings', 'settings'])
    const progressPatch = Object.fromEntries(
        Object.entries(incomingProgress).filter(([key]) => allowedProgressKeys.has(key))
    )
    const projectPayloadPatch = Object.fromEntries(
        Object.entries(incomingProjectPayload).filter(([key]) => allowedProjectPayloadKeys.has(key))
    )
    const titlePatch = typeof body?.title === 'string' ? body.title.trim() : ''

    if (Object.keys(progressPatch).length === 0 && Object.keys(projectPayloadPatch).length === 0 && !titlePatch && incomingScenes.length === 0) {
        return NextResponse.json({ success: false, error: 'No supported fields to update' }, { status: 400 })
    }

    const updatePayload: Record<string, any> = {
        updated_at: new Date().toISOString(),
    }
    if (Object.keys(progressPatch).length > 0) {
        updatePayload.progress_payload = {
            ...(project.progress_payload || {}),
            ...progressPatch,
        }
    }
    if (Object.keys(projectPayloadPatch).length > 0) {
        updatePayload.project_payload = {
            ...(project.project_payload || {}),
            ...projectPayloadPatch,
        }
    }
    if (titlePatch) updatePayload.title = titlePatch

    const { data: updated, error: updateError } = await supabaseAdmin
        .from('std_projects')
        .update(updatePayload)
        .eq('id', project.id)
        .select('*')
        .single()

    if (updateError) return NextResponse.json({ success: false, error: updateError.message }, { status: 500 })

    let updatedScenes: any[] | null = null
    if (incomingScenes.length > 0) {
        const normalizedScenes = incomingScenes
            .map((scene: any, index: number) => {
                const sceneNumber = Number(scene?.scene_number || index + 1)
                if (!Number.isFinite(sceneNumber) || sceneNumber <= 0) return null
                return {
                    scene_number: Math.floor(sceneNumber),
                    scene_title: String(scene?.scene_title || scene?.title || `Scene ${Math.floor(sceneNumber)}`).slice(0, 500),
                    scene_text: String(scene?.text || scene?.script_excerpt || scene?.scene_text || '').slice(0, 10000),
                    image_prompt: String(scene?.image_prompt || scene?.prompt || '').slice(0, 20000),
                    video_prompt: String(scene?.video_prompt || '').slice(0, 20000),
                    metadata: {
                        ...(scene?.metadata || {}),
                        script_excerpt: scene?.script_excerpt || scene?.text || scene?.scene_text || '',
                        visual_type: scene?.visual_type || null,
                    },
                }
            })
            .filter(Boolean) as any[]

        const { data: existingScenes, error: existingScenesError } = await supabaseAdmin
            .from('std_project_scenes')
            .select('id,scene_number')
            .eq('project_id', project.id)
        if (existingScenesError) return NextResponse.json({ success: false, error: existingScenesError.message }, { status: 500 })

        const existingBySceneNumber = new Map((existingScenes || []).map((scene: any) => [Number(scene.scene_number), scene]))
        const updates = normalizedScenes
            .filter(scene => existingBySceneNumber.has(Number(scene.scene_number)))
            .map(scene => supabaseAdmin
                .from('std_project_scenes')
                .update({
                    scene_title: scene.scene_title,
                    scene_text: scene.scene_text,
                    image_prompt: scene.image_prompt,
                    video_prompt: scene.video_prompt,
                    metadata: scene.metadata,
                    updated_at: new Date().toISOString(),
                })
                .eq('id', existingBySceneNumber.get(Number(scene.scene_number))?.id)
            )
        const inserts = normalizedScenes
            .filter(scene => !existingBySceneNumber.has(Number(scene.scene_number)))
            .map(scene => ({
                ...scene,
                project_id: project.id,
                asset_status: 'missing',
            }))

        const updateResults = await Promise.all(updates)
        const failedUpdate = updateResults.find((result: any) => result.error)
        if (failedUpdate?.error) return NextResponse.json({ success: false, error: failedUpdate.error.message }, { status: 500 })

        if (inserts.length > 0) {
            const { error: insertScenesError } = await supabaseAdmin.from('std_project_scenes').insert(inserts)
            if (insertScenesError) return NextResponse.json({ success: false, error: insertScenesError.message }, { status: 500 })
        }

        const { data: scenesAfterSave, error: scenesAfterSaveError } = await supabaseAdmin
            .from('std_project_scenes')
            .select('id,project_id,scene_number,scene_title,scene_text,image_prompt,video_prompt,asset_status,metadata,created_at,updated_at')
            .eq('project_id', project.id)
            .order('scene_number', { ascending: true })
        if (scenesAfterSaveError) return NextResponse.json({ success: false, error: scenesAfterSaveError.message }, { status: 500 })
        updatedScenes = scenesAfterSave || []
    }

    return NextResponse.json({ success: true, project: updated, scenes: updatedScenes })
}
