import { isStdRequiredVideoScene, stdRequiredVideoSceneCount } from './stdPolicy'

// Image-page completion: opening video clips plus a saved visual for every
// remaining scene. Later animation/render review has its own readiness gates.
export function savedStdVisualStepStatus(project: any, assets: any[] = []) {
    const payload = project.project_payload || {}
    const scenes = Array.isArray(payload.scenes) && payload.scenes.length
        ? payload.scenes : (Array.isArray(payload.structure?.scenes) ? payload.structure.scenes : [])
    const media = assets.filter(asset => ['uploaded', 'assigned'].includes(asset.status)
        && asset.id && (asset.metadata?.gcs_path || asset.metadata?.storage_path
            || asset.metadata?.gcs_signed_url || asset.metadata?.gcs_public_url))
    const uploadedAssetsCount = scenes.filter((scene: any, index: number) => {
        const number = Number(scene.scene_number || scene.scene_order || index + 1)
        const matching = media.filter(asset => Number(asset.scene_number) === number)
        const video = Boolean(scene.video_url || matching.some(asset => asset.asset_type === 'video'))
        return isStdRequiredVideoScene(number, project) ? video
            : Boolean(video || scene.image_url || matching.some(asset => asset.asset_type === 'image'))
    }).length
    const isImageDone = scenes.length > 0 && uploadedAssetsCount === scenes.length
    const structures = [payload.structure, payload.pregenerated_structure,
        project.source_payload?.pregenerated_structure, project.source_payload?.structure]
    const extraVideoScenes = new Set<number>()
    structures.forEach(structure => {
        if (Array.isArray(structure?.motion_graphic_video_scenes)) structure.motion_graphic_video_scenes.forEach((value: unknown) => {
            const number = Number(value)
            if (Number.isInteger(number) && number > 0) extraVideoScenes.add(number)
        })
    })
    scenes.forEach((scene: any, index: number) => {
        if (scene.video_prompt_required === true || scene.video_generation_mode === 'user_upload')
            extraVideoScenes.add(Number(scene.scene_number || scene.scene_order || index + 1))
    })
    const extraVideosReady = [...extraVideoScenes].every(number => scenes.some((scene: any, index: number) =>
        Number(scene.scene_number || scene.scene_order || index + 1) === number && Boolean(scene.video_url))
        || media.some(asset => Number(asset.scene_number) === number && asset.asset_type === 'video'))
    const isVideoStepDone = extraVideoScenes.size > 0 ? isImageDone && extraVideosReady
        : isImageDone || stdRequiredVideoSceneCount(project) === 0
    return { isImageDone, isVideoStepDone,
        uploadedAssetsCount, totalScenesCount: scenes.length }
}
