/** Choose a durable URL; browser-local object URLs cannot survive a new session. */
export function persistentThumbnailUrl(...values: unknown[]): string {
    for (const value of values) {
        if (typeof value !== 'string') continue
        const url = value.trim()
        if (/^https?:\/\//i.test(url) || (url.startsWith('/') && !url.startsWith('//'))) return url
    }
    return ''
}
