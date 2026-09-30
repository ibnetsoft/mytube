export type GcsCharacterObject = { bucket: string; path: string }

export function gcsCharacterObjectFromUrl(value: unknown, baseUrl: string): GcsCharacterObject | null {
    const raw = String(value || '').trim()
    if (!raw) return null
    try {
        const base = new URL(baseUrl)
        const url = new URL(raw, base)
        if (url.origin !== base.origin || url.pathname !== '/api/std/assets/gcs-file') return null
        const bucket = String(url.searchParams.get('bucket') || '').trim()
        const path = String(url.searchParams.get('path') || '').trim().replace(/^\/+/, '')
        if (!bucket || !/^topics\/\d+\/characters\/[^/]+\.(?:png|jpe?g|webp|gif)$/i.test(path)) return null
        return { bucket, path }
    } catch {
        return null
    }
}

export function characterImageContentType(path: string): string {
    const lower = path.toLowerCase()
    if (lower.endsWith('.png')) return 'image/png'
    if (lower.endsWith('.jpg') || lower.endsWith('.jpeg')) return 'image/jpeg'
    if (lower.endsWith('.webp')) return 'image/webp'
    if (lower.endsWith('.gif')) return 'image/gif'
    return 'application/octet-stream'
}
