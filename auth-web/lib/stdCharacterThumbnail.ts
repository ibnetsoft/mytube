export type GcsCharacterObject = { bucket: string; path: string }

function isAuthorizedCharacterPath(path: string): boolean {
    const segments = path.split('/')
    if (segments[0] !== 'topics') return false

    let charactersIndex = -1
    if (/^\d+$/.test(segments[1] || '')) {
        charactersIndex = 2
    } else if (segments[1] === 'prepared' && /^[A-Za-z0-9_-]+$/.test(segments[2] || '')) {
        charactersIndex = 3
    }
    if (charactersIndex < 0 || segments[charactersIndex] !== 'characters') return false

    const assetSegments = segments.slice(charactersIndex + 1)
    if (assetSegments.length < 1) return false
    if (!assetSegments.every(segment => /^[A-Za-z0-9._-]+$/.test(segment) && segment !== '.' && segment !== '..')) return false
    return /\.(?:png|jpe?g|webp|gif)$/i.test(assetSegments[assetSegments.length - 1])
}

export function gcsCharacterObjectFromUrl(value: unknown, baseUrl: string): GcsCharacterObject | null {
    const raw = String(value || '').trim()
    if (!raw) return null
    try {
        const base = new URL(baseUrl)
        const url = new URL(raw, base)
        if (url.origin !== base.origin || url.pathname !== '/api/std/assets/gcs-file') return null
        const bucket = String(url.searchParams.get('bucket') || '').trim()
        const path = String(url.searchParams.get('path') || '').trim().replace(/^\/+/, '')
        if (!bucket || !isAuthorizedCharacterPath(path)) return null
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
