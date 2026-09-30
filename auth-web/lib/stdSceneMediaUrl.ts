type SceneLike = {
    image_url?: unknown
    image?: unknown
    metadata?: any
}

function text(value: unknown): string {
    return String(value || '').trim()
}

function gcsProxyUrl(bucket: unknown, objectPath: unknown): string {
    const safeBucket = text(bucket)
    const safePath = text(objectPath).replace(/^\/+/, '')
    if (!safeBucket || !safePath || safePath.includes('..')) return ''
    const query = new URLSearchParams({ bucket: safeBucket, path: safePath })
    return `/api/std/assets/gcs-file?${query.toString()}`
}

function legacyTopicGcsUrl(value: unknown): string {
    const raw = text(value)
    if (!raw) return ''
    try {
        const url = new URL(raw)
        const match = url.pathname.match(/^\/storage\/v1\/object\/public\/([^/]+)\/(.+)$/)
        if (!match) return ''
        const bucket = decodeURIComponent(match[1])
        const objectPath = decodeURIComponent(match[2])
        // Older topic image records stored a GCS bucket/object as if it were
        // a Supabase public bucket URL. Those buckets do not exist in Supabase.
        if (bucket !== 'air-studio-prod' || !/(?:^|\/)topics\/\d+\/images\//.test(objectPath)) return ''
        return gcsProxyUrl(bucket, objectPath)
    } catch {
        return ''
    }
}

export function sceneImageUrl(scene: SceneLike | null | undefined): string {
    const metadata = scene?.metadata || {}
    const nested = metadata?.metadata || {}
    const asset = metadata?.cowork_image_asset || nested?.cowork_image_asset || {}
    const provider = text(asset?.storage_provider || metadata?.storage_provider || nested?.storage_provider).toLowerCase()
    const objectPaths = [
        asset?.gcs_path, metadata?.gcs_path, nested?.gcs_path,
        asset?.object_path, metadata?.object_path, nested?.object_path,
        asset?.storage_path, metadata?.storage_path, nested?.storage_path,
    ].map(text).filter(Boolean)
    const isLegacyTopicGcs = (path: string) => /(?:^|\/)topics\/\d+\/images\//.test(path.replace(/^\/+/, ''))
    const gcsPath = objectPaths.find(path => provider === 'gcs' || isLegacyTopicGcs(path))
    const gcsBucket = asset?.gcs_bucket || metadata?.gcs_bucket || nested?.gcs_bucket
        || (gcsPath ? asset?.bucket || metadata?.bucket || nested?.bucket : '')
    const gcsUrl = gcsProxyUrl(gcsBucket, gcsPath)
    if (gcsUrl) return gcsUrl

    const legacyUrl = legacyTopicGcsUrl(scene?.image_url || scene?.image)
        || legacyTopicGcsUrl(metadata?.image_url || metadata?.image || nested?.image_url || nested?.image)
    if (legacyUrl) return legacyUrl

    return text(scene?.image_url || scene?.image)
        || text(metadata?.image_url || metadata?.image || nested?.image_url || nested?.image)
}
