export type AeSceneDelivery = 'gcs'

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
    if (selected !== 'gcs') {
        throw new Error('Invalid AE scene delivery')
    }
    return selected
}

export function resolveClaimAeSceneDelivery(structure: any, selected?: AeSceneDelivery): AeSceneDelivery {
    void structure
    void selected
    return 'gcs'
}
