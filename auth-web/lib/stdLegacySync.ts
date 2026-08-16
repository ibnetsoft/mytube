import { supabaseAdmin } from './supabaseAdmin'
import { driveFileLink, driveFolderLink } from './stdGoogleDrive'
import { isStdRequiredVideoScene } from './stdPolicy'

const DESKTOP_PROJECT_TABLE = 'desktop_project_metadata'

function nowIso() {
    return new Date().toISOString()
}

function wordCount(text: string): number {
    return String(text || '').split(/\s+/).map((part) => part.trim()).filter(Boolean).length
}

function sceneAssetsFor(assets: any[], sceneNumber: number, assetType?: string) {
    return assets.filter((asset: any) =>
        Number(asset.scene_number) === Number(sceneNumber)
        && (!assetType || asset.asset_type === assetType)
        && ['uploaded', 'assigned'].includes(String(asset.status || ''))
    )
}

function buildSteps(project: any, scenes: any[], assets: any[]) {
    const publishMetadata = project?.project_payload?.publish_metadata || project?.progress_payload?.publish_metadata || {}
    const readySceneNumbers = new Set(
        assets
            .filter((asset: any) => ['image', 'video'].includes(asset.asset_type) && ['uploaded', 'assigned'].includes(asset.status))
            .map((asset: any) => Number(asset.scene_number))
            .filter(Number.isFinite)
    )
    const readyVideoSceneNumbers = new Set(
        assets
            .filter((asset: any) => asset.asset_type === 'video' && ['uploaded', 'assigned'].includes(asset.status))
            .map((asset: any) => Number(asset.scene_number))
            .filter(Number.isFinite)
    )
    const allScenesReady = scenes.length > 0 && scenes.every((scene: any) => {
        const sceneNumber = Number(scene.scene_number)
        return isStdRequiredVideoScene(sceneNumber)
            ? readyVideoSceneNumbers.has(sceneNumber)
            : readySceneNumbers.has(sceneNumber)
    })

    return {
        topic: true,
        plan: true,
        script: Boolean(project?.project_payload?.script),
        intro: false,
        image: allScenesReady,
        template: false,
        tts: false,
        subtitle: false,
        video: false,
        upload: ['review_requested', 'approved'].includes(String(project?.status || '')),
        desc: Boolean(String(publishMetadata?.description || '').trim()),
    }
}

function buildProgressPayload(project: any, scenes: any[], assets: any[]) {
    const steps = buildSteps(project, scenes, assets)
    const completedStepKeys = Object.entries(steps)
        .filter(([, done]) => Boolean(done))
        .map(([key]) => key)
    const readySceneCount = scenes.filter((scene: any) => scene.asset_status === 'ready').length
    const submitted = ['review_requested', 'approved'].includes(String(project?.status || ''))

    return {
        project_id: null,
        std_web_project_id: project.id,
        sync_id: `std-web-${project.id}`,
        topic_queue_id: project.topic_queue_id,
        project_name: project.title || '',
        project_status: submitted ? 'remote_queued' : project.status || 'in_progress',
        completed_step_keys: completedStepKeys,
        completed_steps: completedStepKeys,
        current_step_key: submitted ? 'upload' : readySceneCount >= scenes.length ? 'upload' : 'image',
        current_step: submitted ? 'submitted' : readySceneCount >= scenes.length ? 'upload' : 'image',
        completed_count: completedStepKeys.length,
        scene_count: scenes.length,
        ready_scene_count: readySceneCount,
        drive_folder_id: project.drive_folder_id || null,
        drive_folder_link: project.drive_folder_id ? driveFolderLink(project.drive_folder_id) : null,
        publish_metadata: project?.project_payload?.publish_metadata || {},
        source: 'std_web',
        steps,
        synced_at: nowIso(),
    }
}

function buildProjectPayload(project: any, scenes: any[], assets: any[]) {
    const script = String(project?.project_payload?.script || '')
    const imagePrompts = scenes.map((scene: any) => {
        const image = sceneAssetsFor(assets, scene.scene_number, 'image')[0]
        const video = sceneAssetsFor(assets, scene.scene_number, 'video')[0]
        return {
            scene_number: scene.scene_number,
            prompt: '',
            image_prompt: '',
            video_prompt: scene.video_prompt || '',
            image_url: image?.drive_file_id ? driveFileLink(image.drive_file_id) : null,
            video_url: video?.drive_file_id ? driveFileLink(video.drive_file_id) : null,
            image_drive_file_id: image?.drive_file_id || null,
            video_drive_file_id: video?.drive_file_id || null,
            scene_text: scene.scene_text || '',
            scene_title: scene.scene_title || '',
        }
    })

    return {
        version: 1,
        source: 'std_web',
        project: {
            id: null,
            sync_id: `std-web-${project.id}`,
            name: project.title,
            topic: project.title,
            status: project.status,
            language: project.language,
            employee_email: project.employee_email,
        },
        settings: {
            app_mode: 'longform',
            topic_queue_id: project.topic_queue_id,
            target_language: project.language || 'ko',
            script_style: project.script_style || 'default',
            image_style: project.image_style || 'realistic',
            assigned_duration_minutes: project.assigned_duration_minutes,
            estimated_payout: project.estimated_payout,
            drive_folder_id: project.drive_folder_id || null,
            std_web_project_id: project.id,
        },
        script_structure: project?.project_payload?.structure || {},
        script: {
            full_script: script,
            word_count: wordCount(script),
            estimated_duration: project.assigned_duration_minutes ? Number(project.assigned_duration_minutes) * 60 : null,
        },
        image_prompts: imagePrompts,
        metadata: project?.project_payload?.publish_metadata || {},
        local_media: {
            image_count: assets.filter((asset: any) => asset.asset_type === 'image' && ['uploaded', 'assigned'].includes(asset.status)).length,
            video_scene_count: assets.filter((asset: any) => asset.asset_type === 'video' && ['uploaded', 'assigned'].includes(asset.status)).length,
            has_project_video: false,
            has_tts_audio: assets.some((asset: any) => asset.asset_type === 'audio' && ['uploaded', 'assigned'].includes(asset.status)),
            has_thumbnail: assets.some((asset: any) => asset.asset_type === 'thumbnail' && ['uploaded', 'assigned'].includes(asset.status)),
            storage: 'google_drive',
        },
    }
}

async function loadStdBundle(projectId: string) {
    const { data: project, error: projectError } = await supabaseAdmin
        .from('std_projects')
        .select('*')
        .eq('id', projectId)
        .maybeSingle()
    if (projectError) throw projectError
    if (!project) return null

    const [{ data: scenes, error: scenesError }, { data: assets, error: assetsError }] = await Promise.all([
        supabaseAdmin
            .from('std_project_scenes')
            .select('*')
            .eq('project_id', project.id)
            .order('scene_number', { ascending: true }),
        supabaseAdmin
            .from('std_project_assets')
            .select('*')
            .eq('project_id', project.id)
            .order('created_at', { ascending: false }),
    ])
    if (scenesError) throw scenesError
    if (assetsError) throw assetsError
    return { project, scenes: scenes || [], assets: assets || [] }
}

export async function syncStdProjectToLegacy(projectId: string) {
    const bundle = await loadStdBundle(projectId)
    if (!bundle) return false

    const { project, scenes, assets } = bundle
    const progressPayload = buildProgressPayload(project, scenes, assets)
    const projectPayload = buildProjectPayload(project, scenes, assets)
    const syncId = `std-web-${project.id}`
    const now = nowIso()

    await supabaseAdmin
        .from(DESKTOP_PROJECT_TABLE)
        .upsert({
            sync_id: syncId,
            user_id: project.user_id,
            employee_email: project.employee_email,
            local_project_id: null,
            name: project.title,
            topic: project.title,
            status: project.status,
            language: project.language || 'ko',
            app_mode: 'longform',
            project_payload: projectPayload,
            progress_payload: progressPayload,
            deleted_at: null,
            updated_at: now,
            synced_at: now,
        }, { onConflict: 'sync_id' })

    if (project.topic_queue_id != null) {
        await supabaseAdmin
            .from('topics_queue')
            .update({
                progress_payload: progressPayload,
                progress_updated_at: now,
            })
            .eq('id', project.topic_queue_id)
    }

    return true
}
