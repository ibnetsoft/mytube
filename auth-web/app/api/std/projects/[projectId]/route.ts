import { canEditStdProject } from '@/lib/stdProjectEditPolicy'
import { NextResponse } from 'next/server'
import { supabaseAdmin } from '@/lib/supabaseAdmin'
import { requireStdUser } from '@/lib/stdWeb'
import { isStdRequiredVideoScene } from '@/lib/stdPolicy'

export const dynamic = 'force-dynamic'

const CONTENT_ASSETS_BUCKET = 'content-assets'

function cleanUrl(value: any): string {
    const str = String(value || '').trim()
    if (!str || str.startsWith('blob:')) return ''
    return str
}

function jsonObject(value: any): Record<string, any> {
    if (value && typeof value === 'object' && !Array.isArray(value)) return value
    if (typeof value !== 'string' || !value.trim()) return {}
    try {
        const parsed = JSON.parse(value)
        return parsed && typeof parsed === 'object' && !Array.isArray(parsed) ? parsed : {}
    } catch {
        return {}
    }
}

function projectTopicQueueId(project: any): number | null {
    const projectPayload = jsonObject(project?.project_payload)
    const sourcePayload = jsonObject(project?.source_payload)
    const candidates = [
        project?.topic_queue_id,
        projectPayload?.topic_queue_id,
        projectPayload?.topic_id,
        sourcePayload?.id,
        sourcePayload?.topic_queue_id,
        sourcePayload?.topic_id,
    ]
    for (const candidate of candidates) {
        const topicId = Number(candidate)
        if (Number.isFinite(topicId) && topicId > 0) return Math.floor(topicId)
    }
    return null
}

function structureScenes(value: any): any[] {
    const structure = jsonObject(value)
    return Array.isArray(structure?.scenes) ? structure.scenes : []
}

function storagePublicUrl(bucket: any, objectPath: any): string {
    const path = String(objectPath || '').trim().replace(/^\/+/, '')
    if (!path) return ''
    const safeBucket = String(bucket || CONTENT_ASSETS_BUCKET).trim() || CONTENT_ASSETS_BUCKET
    const { data } = supabaseAdmin.storage.from(safeBucket).getPublicUrl(path)
    return cleanUrl(data?.publicUrl)
}

function sceneNumberOf(scene: any, fallback = 0): number {
    const value = Number(scene?.scene_number || scene?.scene_order || fallback)
    return Number.isFinite(value) && value > 0 ? Math.floor(value) : fallback
}

function isSupabaseStorageUrl(value: any): boolean {
    const url = cleanUrl(value)
    return url.includes('/storage/v1/object/') || url.includes('/storage/v1/render/')
}

function sceneSupabaseImageUrl(scene: any): string {
    const metadata = scene?.metadata || {}
    const nestedMetadata = metadata?.metadata || {}
    const coworkAsset = metadata?.cowork_image_asset || nestedMetadata?.cowork_image_asset || {}
    const directUrl = cleanUrl(scene?.image_url || scene?.image)
        || cleanUrl(metadata?.image_url || metadata?.image || nestedMetadata?.image_url || nestedMetadata?.image)
    return (isSupabaseStorageUrl(directUrl) ? directUrl : '')
        || storagePublicUrl(coworkAsset?.bucket || metadata?.bucket || nestedMetadata?.bucket, coworkAsset?.object_path || metadata?.object_path || nestedMetadata?.object_path)
        || storagePublicUrl(
            metadata?.storage_bucket || nestedMetadata?.storage_bucket,
            metadata?.storage_path || metadata?.storage_object_path || nestedMetadata?.storage_path || nestedMetadata?.storage_object_path
        )
}

function sceneStorageImageUrl(scene: any): string {
    const metadata = scene?.metadata || {}
    const nestedMetadata = metadata?.metadata || {}
    return sceneSupabaseImageUrl(scene)
        || cleanUrl(scene?.image_url || scene?.image)
        || cleanUrl(metadata?.image_url || metadata?.image || nestedMetadata?.image_url || nestedMetadata?.image)
}

function sceneSupabaseVideoUrl(scene: any): string {
    const metadata = scene?.metadata || {}
    const nestedMetadata = metadata?.metadata || {}
    const coworkAsset = metadata?.cowork_video_asset || nestedMetadata?.cowork_video_asset || {}
    const directUrl = cleanUrl(scene?.video_url || scene?.video)
        || cleanUrl(metadata?.video_url || metadata?.video || nestedMetadata?.video_url || nestedMetadata?.video)
    const supabaseUrl = isSupabaseStorageUrl(directUrl) ? directUrl : ''
    return supabaseUrl
        || storagePublicUrl(
            coworkAsset?.bucket || metadata?.video_storage_bucket || nestedMetadata?.video_storage_bucket,
            coworkAsset?.object_path || metadata?.video_storage_path || metadata?.video_storage_object_path || nestedMetadata?.video_storage_path || nestedMetadata?.video_storage_object_path
        )
}

function sceneStorageVideoUrl(scene: any): string {
    const metadata = scene?.metadata || {}
    const nestedMetadata = metadata?.metadata || {}
    return sceneSupabaseVideoUrl(scene)
        || cleanUrl(scene?.video_url || scene?.video)
        || cleanUrl(metadata?.video_url || metadata?.video || nestedMetadata?.video_url || nestedMetadata?.video)
}

function sceneMediaAsset(scene: any, assetType: 'image' | 'video', assets: any[] = []) {
    const sceneId = String(scene?.id || '').trim()
    const sceneNumber = Number(scene?.scene_number || scene?.scene_order || 0)
    return (assets || []).find((asset: any) => {
        if (String(asset?.asset_type || '').toLowerCase() !== assetType) return false
        if (sceneId && String(asset?.scene_id || '').trim() === sceneId) return true
        return Number.isFinite(sceneNumber) && sceneNumber > 0 && Number(asset?.scene_number) === sceneNumber
    }) || null
}

function assetSupabaseUrl(asset: any): string {
    const metadata = asset?.metadata || {}
    return cleanUrl(metadata?.storage_public_url)
        || storagePublicUrl(metadata?.storage_bucket, metadata?.storage_path)
}

function hydrateSceneMedia(scene: any, assets: any[] = [], sourceScene?: any) {
    // A scene upload is the user's explicit replacement, so surface its
    // Supabase copy immediately. Topic media remains the fallback.
    const imageAsset = sceneMediaAsset(scene, 'image', assets)
    const videoAsset = sceneMediaAsset(scene, 'video', assets)
    const imageUrl = assetSupabaseUrl(imageAsset)
        || sceneSupabaseImageUrl(scene)
        || sceneSupabaseImageUrl(sourceScene)
        || sceneStorageImageUrl(scene)
        || sceneStorageImageUrl(sourceScene)
    const videoUrl = assetSupabaseUrl(videoAsset)
        || sceneSupabaseVideoUrl(scene)
        || sceneSupabaseVideoUrl(sourceScene)
        || sceneStorageVideoUrl(scene)
        || sceneStorageVideoUrl(sourceScene)
    return {
        ...scene,
        metadata: {
            ...(scene?.metadata || {}),
            ...(imageAsset?.id ? { image_asset_id: imageAsset.id } : {}),
            ...(videoAsset?.id ? { video_asset_id: videoAsset.id } : {}),
        },
        ...(imageUrl ? { image_url: imageUrl } : {}),
        ...(videoUrl ? { video_url: videoUrl } : {}),
    }
}

function payloadScenes(project: any): any[] {
    const payload = project?.project_payload || {}
    const structureScenes = Array.isArray(payload?.structure?.scenes) ? payload.structure.scenes : []
    const scenes = Array.isArray(payload?.scenes) ? payload.scenes : []
    return [...structureScenes, ...scenes]
}

function findSceneByNumber(scenes: any[], sceneNumber: number) {
    return (scenes || []).find((scene: any, index: number) => {
        const candidate = Number(scene?.scene_number || scene?.scene_order || index + 1)
        return candidate === sceneNumber
    })
}

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
    if (!project) {
        return new NextResponse(null, { status: 204, headers: { 'Cache-Control': 'no-store' } })
    }

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

    const sourceSceneByNumber = new Map<number, any>()
    const sourcePayload = jsonObject(project?.source_payload)
    for (const [index, scene] of structureScenes(sourcePayload?.pregenerated_structure).entries()) {
        sourceSceneByNumber.set(sceneNumberOf(scene, index + 1), scene)
    }

    const topicQueueId = projectTopicQueueId(project)
    if (topicQueueId) {
        const { data: topic } = await supabaseAdmin
            .from('topics_queue')
            .select('pregenerated_structure')
            .eq('id', topicQueueId)
            .maybeSingle()
        for (const [index, scene] of structureScenes(topic?.pregenerated_structure).entries()) {
            sourceSceneByNumber.set(sceneNumberOf(scene, index + 1), scene)
        }
    }

    return NextResponse.json({
        success: true,
        project,
        scenes: (scenes || []).map((scene, index) => hydrateSceneMedia(
            scene,
            assets || [],
            sourceSceneByNumber.get(sceneNumberOf(scene, index + 1))
        )),
        assets: assets || [],
    })
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
    if (!canEditStdProject(project.status, body)) {
        return NextResponse.json({ success: false, error: 'Project is not editable' }, { status: 409 })
    }

    const incomingProgress = body?.progress_payload || {}
    const incomingProjectPayload = body?.project_payload || {}
    const allowSceneUpdate = body?.allow_scene_update === true
    const allowSceneInsert = body?.allow_scene_insert === true
    const incomingScenes = allowSceneUpdate && Array.isArray(incomingProjectPayload?.scenes) ? incomingProjectPayload.scenes : []
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
    if (!allowSceneUpdate) {
        delete (projectPayloadPatch as any).scenes
        if (
            projectPayloadPatch.structure
            && typeof projectPayloadPatch.structure === 'object'
            && !Array.isArray(projectPayloadPatch.structure)
        ) {
            const { scenes: _ignoredScenes, ...structureWithoutScenes } = projectPayloadPatch.structure as any
            projectPayloadPatch.structure = structureWithoutScenes
        }
    }
    const canonicalOriginalWorkerScript = await resolveOriginalWorkerScript(project)
    if (canonicalOriginalWorkerScript) {
        projectPayloadPatch.original_worker_script = canonicalOriginalWorkerScript
    }
    const titlePatch = typeof body?.title === 'string' ? body.title.trim() : ''

    if (Object.keys(progressPatch).length === 0 && Object.keys(projectPayloadPatch).length === 0 && !titlePatch && incomingScenes.length === 0) {
        return NextResponse.json({ success: false, error: 'No supported fields to update' }, { status: 400 })
    }

    const currentPayloadScenes = payloadScenes(project)
    const normalizedScenes = incomingScenes.length > 0
        ? incomingScenes
            .map((scene: any, index: number) => {
                const sceneNumber = Number(scene?.scene_number || index + 1)
                if (!Number.isFinite(sceneNumber) || sceneNumber <= 0) return null
                const normalizedSceneNumber = Math.floor(sceneNumber)
                const requiresVideoPrompt = isStdRequiredVideoScene(normalizedSceneNumber)
                const currentScene = findSceneByNumber(currentPayloadScenes, normalizedSceneNumber) || {}
                const imageUrl = sceneSupabaseImageUrl(scene)
                    || sceneSupabaseImageUrl(currentScene)
                    || sceneStorageImageUrl(scene)
                    || sceneStorageImageUrl(currentScene)
                const videoUrl = sceneSupabaseVideoUrl(scene)
                    || sceneSupabaseVideoUrl(currentScene)
                    || sceneStorageVideoUrl(scene)
                    || sceneStorageVideoUrl(currentScene)
                return {
                    scene_number: normalizedSceneNumber,
                    scene_order: normalizedSceneNumber,
                    scene_title: String(scene?.scene_title || scene?.title || `Scene ${normalizedSceneNumber}`).slice(0, 500),
                    scene_text: String(scene?.text || scene?.script_excerpt || scene?.scene_text || '').slice(0, 10000),
                    image_prompt: String(scene?.image_prompt || scene?.prompt || '').slice(0, 20000),
                    video_prompt: requiresVideoPrompt ? String(scene?.video_prompt || '').slice(0, 20000) : '',
                    ...(imageUrl ? { image_url: imageUrl } : {}),
                    ...(videoUrl ? { video_url: videoUrl } : {}),
                    metadata: {
                        ...(scene?.metadata || {}),
                        script_excerpt: scene?.script_excerpt || scene?.text || scene?.scene_text || '',
                        visual_type: requiresVideoPrompt ? (scene?.visual_type || 'video') : 'image',
                        video_prompt_required: requiresVideoPrompt,
                        ...(imageUrl ? { image_url: imageUrl } : {}),
                        ...(videoUrl ? { video_url: videoUrl } : {}),
                    },
                }
            })
            .filter(Boolean) as any[]
        : []

    let existingBySceneNumber = new Map<number, any>()
    if (normalizedScenes.length > 0) {
        const { data: existingScenes, error: existingScenesError } = await supabaseAdmin
            .from('std_project_scenes')
            .select('id,scene_number')
            .eq('project_id', project.id)
        if (existingScenesError) return NextResponse.json({ success: false, error: existingScenesError.message }, { status: 500 })
        existingBySceneNumber = new Map((existingScenes || []).map((scene: any) => [Number(scene.scene_number), scene]))
    }
    const persistableScenes = allowSceneInsert
        ? normalizedScenes
        : normalizedScenes.filter(scene => existingBySceneNumber.has(Number(scene.scene_number)))

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
        if (persistableScenes.length > 0) {
            nextStructure.scenes = persistableScenes
        }
        updatePayload.project_payload = {
            ...(project.project_payload || {}),
            ...projectPayloadPatch,
            ...(persistableScenes.length > 0 ? { scenes: persistableScenes } : {}),
            ...(Object.keys(nextStructure).length > 0 ? { structure: nextStructure } : {}),
        }
    }
    if (titlePatch) updatePayload.title = titlePatch

    const { data: updated, error: updateError } = await supabaseAdmin
        .from('std_projects')
        .update(updatePayload)
        .eq('id', project.id)
        .eq('status', project.status)
        .select('*')
        .single()

    if (updateError) return NextResponse.json({ success: false, error: updateError.message }, { status: 500 })

    let updatedScenes: any[] | null = null
    if (normalizedScenes.length > 0) {
        const updates = persistableScenes
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
        const inserts = persistableScenes
            .filter(scene => !existingBySceneNumber.has(Number(scene.scene_number)))
            .map(scene => ({
                ...scene,
                project_id: project.id,
                asset_status: 'missing',
            }))

        const updateResults = await Promise.all(updates)
        const failedUpdate = updateResults.find((result: any) => result.error)
        if (failedUpdate?.error) return NextResponse.json({ success: false, error: failedUpdate.error.message }, { status: 500 })

        if (allowSceneInsert && inserts.length > 0) {
            const { error: insertScenesError } = await supabaseAdmin.from('std_project_scenes').insert(inserts)
            if (insertScenesError) return NextResponse.json({ success: false, error: insertScenesError.message }, { status: 500 })
        }

        const { data: scenesAfterSave, error: scenesAfterSaveError } = await supabaseAdmin
            .from('std_project_scenes')
            .select('id,project_id,scene_number,scene_title,scene_text,image_prompt,video_prompt,asset_status,metadata,created_at,updated_at')
            .eq('project_id', project.id)
            .order('scene_number', { ascending: true })
        if (scenesAfterSaveError) return NextResponse.json({ success: false, error: scenesAfterSaveError.message }, { status: 500 })
        const { data: assetsAfterSave, error: assetsAfterSaveError } = await supabaseAdmin
            .from('std_project_assets')
            .select('id,scene_id,scene_number,asset_type,status,created_at')
            .eq('project_id', project.id)
            .in('status', ['uploaded', 'assigned'])
            .order('created_at', { ascending: false })
        if (assetsAfterSaveError) return NextResponse.json({ success: false, error: assetsAfterSaveError.message }, { status: 500 })
        updatedScenes = (scenesAfterSave || []).map(scene => hydrateSceneMedia(scene, assetsAfterSave || []))
    }

    return NextResponse.json({ success: true, project: updated, scenes: updatedScenes })
}
