import { NextResponse } from 'next/server'
import { supabaseAdmin } from '@/lib/supabaseAdmin'
import { requireStdUser } from '@/lib/stdWeb'
import { isStdRequiredVideoScene } from '@/lib/stdPolicy'

export const dynamic = 'force-dynamic'

function firstScript(...values: any[]): string {
    return values.map(value => String(value || '').trim()).find(Boolean) || ''
}

async function resolveOriginalWorkerScript(project: any): Promise<string> {
    const sourceScript = firstScript(
        project?.source_payload?.pregenerated_script,
        project?.source_payload?.script,
        project?.source_payload?.full_script,
    )
    if (sourceScript) return sourceScript

    const topicQueueId = Number(project?.topic_queue_id)
    if (Number.isFinite(topicQueueId) && topicQueueId > 0) {
        const { data: topic } = await supabaseAdmin
            .from('topics_queue')
            .select('pregenerated_script')
            .eq('id', topicQueueId)
            .maybeSingle()
        const topicScript = firstScript(topic?.pregenerated_script)
        if (topicScript) return topicScript
    }

    return firstScript(
        project?.project_payload?.original_worker_script,
        project?.project_payload?.pregenerated_script,
    )
}

export async function GET(req: Request, { params }: { params: { projectId: string } }) {
    const auth = await requireStdUser(req)
    if (!auth.ok) return auth.response

    const url = new URL(req.url)
    const impersonateTarget = (req.headers.get('x-impersonate-email') || url.searchParams.get('impersonate') || url.searchParams.get('email') || '').trim().toLowerCase()
    let query = supabaseAdmin.from('std_projects').select('*').eq('id', params.projectId)
    if (auth.requester.email && !auth.requester.email.startsWith('admin') && !auth.requester.email.startsWith('worker')) {
        query = query.eq('employee_email', auth.requester.email)
    }
    let { data: project, error } = await query.maybeSingle()
    if (!project && !error && impersonateTarget) {
        const fallback = await supabaseAdmin.from('std_projects').select('*').eq('id', params.projectId).maybeSingle()
        project = fallback.data
        error = fallback.error
    }

    if (error) return NextResponse.json({ success: false, error: error.message }, { status: 500 })
    if (!project) return NextResponse.json({ success: false, error: 'Project not found' }, { status: 404 })

    const originalWorkerScript = await resolveOriginalWorkerScript(project)
    if (originalWorkerScript) {
        project = {
            ...project,
            project_payload: {
                ...(project.project_payload || {}),
                original_worker_script: originalWorkerScript,
            },
        }
    }

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
    const url = new URL(req.url)
    const impersonateTarget = (req.headers.get('x-impersonate-email') || url.searchParams.get('impersonate') || url.searchParams.get('email') || '').trim().toLowerCase()

    let body: any
    try {
        body = await req.json()
    } catch {
        return NextResponse.json({ success: false, error: 'Invalid JSON' }, { status: 400 })
    }

    let { data: project, error: projectError } = await supabaseAdmin
        .from('std_projects')
        .select('*')
        .eq('id', params.projectId)
        .eq('employee_email', auth.requester.email)
        .maybeSingle()
    if (!project && !projectError && impersonateTarget) {
        const fallback = await supabaseAdmin
            .from('std_projects')
            .select('*')
            .eq('id', params.projectId)
            .maybeSingle()
        project = fallback.data
        projectError = fallback.error
    }

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
        'bgm_sfx_saved',
    ])
    const allowedProjectPayloadKeys = new Set([
        'script',
        'original_worker_script',
        'subtitles',
        'subtitles_saved',
        'title',
        'video_title',
        'scenes',
        'structure',
        'render_settings',
        'settings',
        'thumbnail_design',
        'thumbnail_url',
        'bgm_sfx_saved',
    ])
    const progressPatch = Object.fromEntries(
        Object.entries(incomingProgress).filter(([key]) => allowedProgressKeys.has(key))
    )
    const projectPayloadPatch = Object.fromEntries(
        Object.entries(incomingProjectPayload).filter(([key]) => allowedProjectPayloadKeys.has(key))
    )
    const canonicalOriginalWorkerScript = await resolveOriginalWorkerScript(project)
    if (canonicalOriginalWorkerScript) {
        projectPayloadPatch.original_worker_script = canonicalOriginalWorkerScript
    }
    const titlePatch = typeof body?.title === 'string' ? body.title.trim() : ''

    if (Object.keys(progressPatch).length === 0 && Object.keys(projectPayloadPatch).length === 0 && !titlePatch && incomingScenes.length === 0) {
        return NextResponse.json({ success: false, error: 'No supported fields to update' }, { status: 400 })
    }

    const normalizedScenes = incomingScenes.length > 0
        ? incomingScenes
            .map((scene: any, index: number) => {
                const sceneNumber = Number(scene?.scene_number || index + 1)
                if (!Number.isFinite(sceneNumber) || sceneNumber <= 0) return null
                const normalizedSceneNumber = Math.floor(sceneNumber)
                const requiresVideoPrompt = isStdRequiredVideoScene(normalizedSceneNumber)
                return {
                    scene_number: normalizedSceneNumber,
                    scene_title: String(scene?.scene_title || scene?.title || `Scene ${normalizedSceneNumber}`).slice(0, 500),
                    scene_text: String(scene?.text || scene?.script_excerpt || scene?.scene_text || '').slice(0, 10000),
                    image_prompt: String(scene?.image_prompt || scene?.prompt || '').slice(0, 20000),
                    video_prompt: requiresVideoPrompt ? String(scene?.video_prompt || '').slice(0, 20000) : '',
                    metadata: {
                        ...(scene?.metadata || {}),
                        script_excerpt: scene?.script_excerpt || scene?.text || scene?.scene_text || '',
                        visual_type: requiresVideoPrompt ? (scene?.visual_type || 'video') : 'image',
                        video_prompt_required: requiresVideoPrompt,
                    },
                }
            })
            .filter(Boolean) as any[]
        : []

    const updatePayload: Record<string, any> = {
        updated_at: new Date().toISOString(),
    }
    if (Object.keys(progressPatch).length > 0) {
        updatePayload.progress_payload = {
            ...(project.progress_payload || {}),
            ...progressPatch,
        }
    }
    if (Object.keys(projectPayloadPatch).length > 0 || normalizedScenes.length > 0) {
        const currentStructure = project.project_payload?.structure || {}
        const nextStructure = projectPayloadPatch.structure
            ? {
                ...currentStructure,
                ...projectPayloadPatch.structure,
            }
            : currentStructure
        if (normalizedScenes.length > 0) {
            nextStructure.scenes = normalizedScenes
        }
        updatePayload.project_payload = {
            ...(project.project_payload || {}),
            ...projectPayloadPatch,
            ...(normalizedScenes.length > 0 ? { scenes: normalizedScenes } : {}),
            ...(Object.keys(nextStructure).length > 0 ? { structure: nextStructure } : {}),
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
    if (normalizedScenes.length > 0) {
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
