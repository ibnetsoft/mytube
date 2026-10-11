import { gzipSync, gunzipSync } from 'zlib'
import { getServerCache, setServerCache } from './server-cache'

// Versioned entries need no invalidation across independent web/worker writes.
export function projectReadCacheKey(scope: string, projectId: string, version: string) {
    return `std-project-read:v1:${encodeURIComponent(scope)}:${projectId}:${version}`
}
export async function readProjectResponse(key: string) {
    const encoded = await getServerCache<string>(key)
    if (!encoded) return null
    try { return JSON.parse(gunzipSync(Buffer.from(encoded, 'base64')).toString('utf8')) }
    catch { return null }
}
export async function cacheProjectResponse(key: string, value: unknown) {
    const encoded = gzipSync(JSON.stringify(value)).toString('base64')
    // Bound Redis commands; large projects still benefit from the browser cache.
    if (encoded.length <= 900_000) await setServerCache(key, encoded, 60)
}
