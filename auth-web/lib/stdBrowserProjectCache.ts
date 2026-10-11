type Entry = { etag: string; savedAt: number; payload: any }
const DATABASE = 'air-studio-project-cache-v1'

async function database(): Promise<IDBDatabase> {
    return new Promise((resolve, reject) => {
        const request = indexedDB.open(DATABASE, 1)
        request.onupgradeneeded = () => request.result.createObjectStore('projects')
        request.onsuccess = () => resolve(request.result)
        request.onerror = () => reject(request.error)
        request.onblocked = () => reject(new Error('Project cache unavailable'))
    })
}
async function entry(key: string, value?: Entry): Promise<Entry | null> {
    let db: IDBDatabase | undefined
    try {
        db = await database()
        return await new Promise((resolve, reject) => {
            const tx = db!.transaction('projects', value ? 'readwrite' : 'readonly')
            const store = tx.objectStore('projects')
            const request = value ? store.put(value, key) : store.get(key)
            if (value) {
                const entries: { key: IDBValidKey; savedAt: number }[] = []
                const scan = store.openCursor()
                scan.onsuccess = () => {
                    const cursor = scan.result
                    if (cursor) {
                        entries.push({ key: cursor.primaryKey, savedAt: Number(cursor.value?.savedAt) || 0 })
                        cursor.continue()
                    } else {
                        entries.sort((a, b) => b.savedAt - a.savedAt).forEach((item, index) => {
                            if (index >= 20 || Date.now() - item.savedAt > 3_600_000) store.delete(item.key)
                        })
                    }
                }
            }
            tx.oncomplete = () => resolve(value || request.result || null)
            tx.onerror = () => reject(tx.error)
            tx.onabort = () => reject(tx.error)
        })
    } catch { return null } // Private browsing/quota failure must not block work.
    finally { db?.close() }
}

export async function fetchCachedProject(url: string, headers: Record<string, string>, force = false): Promise<Response> {
    // Never store credentials. Separate sessions and impersonated identities.
    const digest = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(`${headers.Authorization}|${headers['x-impersonate-email'] || ''}`))
    const scope = Array.from(new Uint8Array(digest), byte => byte.toString(16).padStart(2, '0')).join('')
    const key = `${scope}:${url}`
    const cached = force ? null : await entry(key)
    const reusable = cached && Date.now() - cached.savedAt < 3_600_000
    const response = await fetch(url, {
        headers: { ...headers, ...(reusable ? { 'If-None-Match': cached.etag } : {}), ...(force ? { 'x-std-refresh': '1' } : {}) },
        cache: 'no-store', signal: AbortSignal.timeout(60000),
    })
    // Authentication/ownership is checked by the server before every 304.
    if (response.status === 304 && reusable) return Response.json(cached.payload)
    if (response.ok && response.headers.get('etag')) {
        const payload = await response.clone().json()
        if (payload?.project) await entry(key, { etag: response.headers.get('etag')!, savedAt: Date.now(), payload })
    }
    return response
}
