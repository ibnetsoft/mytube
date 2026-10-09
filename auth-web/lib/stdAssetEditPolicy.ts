import { isComicProject } from './stdComic'
import { isStdRequiredClipScene } from './stdPolicy'

/** Submitted longform projects may replace an original clip before approval. */
export function canEditStdAsset(project: any, assetType: string, sceneNumber: number | null): boolean {
    const status = String(project?.status || '')
    if (status === 'approved' || status === 'canceled') return false
    if (status !== 'review_requested') return true
    if (['sfx', 'bgm'].includes(assetType) && sceneNumber == null) return true
    return assetType === 'video' && sceneNumber != null && !isComicProject(project)
        && isStdRequiredClipScene(sceneNumber, project)
}
