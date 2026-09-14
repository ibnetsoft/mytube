export const STD_INITIAL_MEDIA_SCENES = [1, 2, 3, 4]

export function directStorageUrl(asset: any): string {
    return String(asset?.metadata?.storage_public_url || '').trim()
}

export function prioritizedSceneNumbers(currentScene: number, totalScenes: number, ahead = 3): number[] {
    const start = Number.isFinite(currentScene) && currentScene > 0 ? Math.floor(currentScene) : 1
    const total = Number.isFinite(totalScenes) && totalScenes > 0 ? Math.floor(totalScenes) : start
    const numbers = start === 1 ? STD_INITIAL_MEDIA_SCENES : Array.from({ length: ahead + 1 }, (_, index) => start + index)
    return [...new Set(numbers)].filter(sceneNumber => sceneNumber >= 1 && sceneNumber <= total)
}

export function selectFallbackAssetsForScenes(
    assets: any[],
    sceneNumbers: number[],
    includeProjectAssets = false,
) {
    const wantedScenes = new Set(sceneNumbers.map(Number))
    return (Array.isArray(assets) ? assets : []).filter((asset: any) => {
        if (!['uploaded', 'assigned'].includes(String(asset?.status || ''))) return false
        const assetType = String(asset?.asset_type || '').toLowerCase()
        if (!['image', 'video', 'thumbnail', 'audio'].includes(assetType)) return false
        if (!(asset?.id || asset?.drive_file_id) || directStorageUrl(asset)) return false
        if (['thumbnail', 'audio'].includes(assetType)) return includeProjectAssets
        return wantedScenes.has(Number(asset?.scene_number))
    }).sort((left: any, right: any) => {
        const leftScene = Number(left?.scene_number)
        const rightScene = Number(right?.scene_number)
        const leftPriority = wantedScenes.has(leftScene) ? sceneNumbers.indexOf(leftScene) : sceneNumbers.length
        const rightPriority = wantedScenes.has(rightScene) ? sceneNumbers.indexOf(rightScene) : sceneNumbers.length
        return leftPriority - rightPriority
    })
}
