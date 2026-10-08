import { isStdRequiredVideoScene } from './stdPolicy'

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
    return { isImageDone: scenes.length > 0 && uploadedAssetsCount === scenes.length,
        uploadedAssetsCount, totalScenesCount: scenes.length }
}
