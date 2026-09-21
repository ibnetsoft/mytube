export const STD_INITIAL_MEDIA_SCENES = [1, 2, 3, 4]

export function directStorageUrl(asset: any): string {
    if (!asset) return ''
    const metadata = asset?.metadata || {}
    const nestedMetadata = metadata?.metadata || {}

    // Stored objects must go through the authorized Supabase-first reader.
    if (metadata.storage_path || metadata.gcs_path) return ''

    // GCS 직접 URL (V4 서명 URL 또는 직접 공용 CDN URL)
    const gcsUrl = String(
        metadata?.gcs_signed_url
        || nestedMetadata?.gcs_signed_url
        || metadata?.gcs_public_url
        || nestedMetadata?.gcs_public_url
        || ''
    ).trim()
    if (gcsUrl) return gcsUrl

    return ''
}

export function resolveFastAssetUrl(
    projectId: string | null | undefined,
    asset: any,
    fallbackUrl?: string | null
): string | null {
    const direct = directStorageUrl(asset)
    if (direct) return direct

    if (projectId && asset?.id && (asset.metadata?.storage_path || asset.metadata?.gcs_path)) {
        return `/api/std/projects/${encodeURIComponent(projectId)}/assets/file?assetId=${encodeURIComponent(asset.id)}`
    }

    const fallback = String(fallbackUrl || '').trim()
    if (fallback && (fallback.startsWith('http://') || fallback.startsWith('https://'))) {
        return fallback
    }

    const id = String(projectId || '').trim()
    const assetId = String(asset?.id || '').trim()
    if (id && assetId) {
        return `/api/std/projects/${encodeURIComponent(id)}/assets/file?assetId=${encodeURIComponent(assetId)}`
    }
    return fallback || null
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
        if (!asset?.id || directStorageUrl(asset)) return false
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
