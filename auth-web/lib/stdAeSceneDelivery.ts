export type AeSceneDelivery = 'local' | 'gcs'

export function parseClaimAeSceneDelivery(rawBody: string): AeSceneDelivery | undefined {
    if (!rawBody.trim()) return undefined
    let body: unknown
    try {
        body = JSON.parse(rawBody)
    } catch {
        throw new Error('Invalid request body')
    }
    if (!body || typeof body !== 'object' || Array.isArray(body)) {
        throw new Error('Invalid request body')
    }
    const selected = (body as Record<string, unknown>).ae_scene_delivery
    if (selected === undefined) return undefined
    if (selected !== 'local' && selected !== 'gcs') {
        throw new Error('Invalid AE scene delivery')
    }
    return selected
}

export function resolveClaimAeSceneDelivery(structure: any, selected?: AeSceneDelivery): AeSceneDelivery {
    if (selected) return selected
    const saved = structure?.ae_scene_delivery
    if (saved === 'local' || saved === 'gcs') return saved
    const hasReadyGcsAsset = Array.isArray(structure?.scenes) && structure.scenes.some((scene: any) => {
        const metadata = scene?.metadata && typeof scene.metadata === 'object' ? scene.metadata : {}
        const readyAsset = ['ae_motion_asset', 'ae_effect_asset'].some(key => {
            const asset = metadata[key]
            return asset?.status === 'ready' && asset?.storage_provider !== 'local'
                && Boolean(asset?.media_url || asset?.gcs_path)
        })
        return readyAsset || Boolean(scene?.ae_motion_video_url || scene?.ae_video_url)
    })
    return hasReadyGcsAsset ? 'gcs' : 'local'
}
