import { comicSettingsForProject, selectComicMedia } from './stdComic'
import { reviewedVideoTail } from './stdVideoTail'
import { motionForProject } from './stdMotionStudio'

export function storageSourceForAsset(asset: any) {
    const metadata = asset?.metadata && typeof asset.metadata === 'object' ? asset.metadata : {}
    const nestedMetadata = metadata?.metadata && typeof metadata.metadata === 'object' ? metadata.metadata : {}
    const bucket = String(metadata?.storage_bucket || nestedMetadata?.storage_bucket || 'content-assets').trim()
    const provider = String(metadata?.storage_provider || nestedMetadata?.storage_provider || '').trim().toLowerCase()
    const path = String(
        metadata?.storage_path
        || metadata?.storage_object_path
        || nestedMetadata?.storage_path
        || nestedMetadata?.storage_object_path
        || ''
    ).trim().replace(/^\/+/, '')
    const gcsBucket = String(metadata?.gcs_bucket || nestedMetadata?.gcs_bucket || (provider === 'gcs' ? bucket : '')).trim()
    const gcsPath = String(metadata?.gcs_path || nestedMetadata?.gcs_path || (provider === 'gcs' ? path : '')).trim().replace(/^\/+/, '')
    if (gcsPath) return { bucket, path: path || gcsPath, provider: 'gcs', gcsBucket, gcsPath }
    return null
}

export function reviewedScenePostprocessAsset(project: any, sceneNumber: number) {
    const structureScenes = project?.project_payload?.structure?.scenes
    if (!Array.isArray(structureScenes)) return null
    const plannedScene = structureScenes.find((scene: any) => Number(scene?.scene_number || scene?.scene_order) === sceneNumber)
    if (!plannedScene) return null
    const effectPlan = plannedScene?.ae_effect_plan && typeof plannedScene.ae_effect_plan === 'object'
        ? plannedScene.ae_effect_plan : {}
    const motionPlan = plannedScene?.ae_motion_plan && typeof plannedScene.ae_motion_plan === 'object'
        ? plannedScene.ae_motion_plan : {}
    const kind = effectPlan.enabled ? 'effect' : motionPlan.enabled ? 'motion' : ''
    if (!kind) return null
    const metadata = plannedScene?.metadata && typeof plannedScene.metadata === 'object' ? plannedScene.metadata : {}
    const plan = kind === 'effect' ? effectPlan : motionPlan
    // Layer templates are allowed only after the exact PSD package passed QA.
    // An unapproved package is ignored and the original visual remains safe.
    if (plan.template) {
        const layered = metadata.psd_layer_asset && typeof metadata.psd_layer_asset === 'object'
            ? metadata.psd_layer_asset : {}
        if (layered.qa_status !== 'approved') return null
    }
    const rendered = metadata[`ae_${kind}_asset`] && typeof metadata[`ae_${kind}_asset`] === 'object'
        ? metadata[`ae_${kind}_asset`] : {}
    const status = String(rendered.status || plannedScene[`ae_${kind}_status`] || '')
    if (status === 'needs_attention') return null
    if (status !== 'ready' && project.project_payload?.submission_pipeline_version === 2) return null
    if (status !== 'ready') {
        const error: any = new Error(`${sceneNumber}번 씬의 AIR STUDIO 후작업을 기다리고 있습니다.`)
        error.code = 'SCENE_POSTPROCESS_PENDING'
        throw error
    }
    const wrapped = {
        asset_type: 'video', scene_number: sceneNumber, status: 'assigned',
        file_name: `scene_${String(sceneNumber).padStart(3, '0')}_air.mp4`, mime_type: 'video/mp4',
        file_size: rendered.file_size || rendered.size || null,
        metadata: rendered,
    }
    // Local-only artifacts are consumed by the Premiere worker. The remote
    // GCS renderer safely uses the original until a reviewed GCS artifact is present.
    return storageSourceForAsset(wrapped) ? wrapped : null
}

/** One authoritative visual selector for frozen continuity review and final composition. */
export function resolveSceneMedia(project: any, scene: any, assets: any[], override?: any) {
    const number = Number(scene.scene_number)
    const originals = [...assets].filter(a => ['uploaded', 'assigned'].includes(String(a.status || ''))
        && Number(a.scene_number) === number && !a.metadata?.ae_mouth_fingerprint && !a.metadata?.lipsync_fingerprint)
        .sort((a, b) => String(b.created_at || '').localeCompare(String(a.created_at || '')) || String(b.id || '').localeCompare(String(a.id || '')))
    const image = originals.find(a => String(a.asset_type).toLowerCase() === 'image')
    const video = originals.find(a => String(a.asset_type).toLowerCase() === 'video')
    if (override) {
        const sourcePath = (video || image)?.metadata?.gcs_path || (video || image)?.metadata?.storage_path
        if (override.metadata?.source_image?.object_path && override.metadata.source_image.object_path !== sourcePath)
            throw Object.assign(new Error(`${number}번 검수 영상의 원본 자산이 현재 씬과 다릅니다.`), { code: 'CONTENT_IDENTITY_MISMATCH' })
        return override
    }
    const draft = motionForProject(project)
    if (draft?.enabled) {
        const choice=draft.scenes[String(number)]?.source || 'auto'
        if (choice==='psd') {
            const prepared=assets.some(a=>Number(a.scene_number)===number && a.metadata?.kind==='ae_scene_preparation' && a.metadata.enabled!==false && a.metadata.state==='prepared')
            if (!prepared) throw new Error(`${number}번 PSD 레이어 준비·검수를 완료해 주세요.`)
            // Reviewed submission output arrives through override; retain the source for continuity snapshots.
            return image || video || null
        }
        const chosen=choice==='image'?image:choice==='video'?video:video||image
        if (!chosen) throw new Error(`${number}번 씬의 선택한 Motion Studio 소스가 없습니다.`)
        return chosen
    }
    const comic = comicSettingsForProject(project), motion = comic.panels[String(number)]?.motion
    if ((motion === 'pan' || motion === 'still') && !image)
        throw new Error(`Scene ${number} needs an image for the selected comic motion`)
    const source = selectComicMedia(motion === 'pan' || motion === 'still' ? 'comic' : comic.mode, image, video)
    let selected = reviewedScenePostprocessAsset(project, number) || reviewedVideoTail(scene, source, project.project_payload)
    const sourcePath = source?.metadata?.gcs_path || source?.metadata?.storage_path
    if (selected?.metadata?.source_image?.object_path && selected.metadata.source_image.object_path !== sourcePath) {
        if (project.project_payload?.submission_pipeline_version === 2) selected = source
        else throw Object.assign(new Error(`${number}번 후처리 영상의 원본 자산이 현재 씬과 다릅니다.`), { code: 'CONTENT_IDENTITY_MISMATCH' })
    }
    return selected || null
}
