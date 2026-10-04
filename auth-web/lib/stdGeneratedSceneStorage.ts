export type GeneratedSceneStorage = {
    provider: 'gcs' | 'supabase'
    bucket: string
    path: string
}

function text(value: unknown): string {
    return String(value || '').trim()
}

function storageRef(provider: GeneratedSceneStorage['provider'], bucket: unknown, path: unknown): GeneratedSceneStorage | null {
    const cleanBucket = text(bucket)
    const cleanPath = text(path).replace(/^\/+/, '')
    if (!cleanBucket || !cleanPath || cleanBucket === '__local__') return null
    return { provider, bucket: cleanBucket, path: cleanPath }
}

function sourceFromUrl(value: unknown, defaultGcsBucket: string): GeneratedSceneStorage | null {
    const raw = text(value)
    if (!raw || raw.startsWith('blob:')) return null
    try {
        const url = new URL(raw, 'https://studio.airing.work')
        if (url.pathname === '/api/std/assets/gcs-file') {
            return storageRef('gcs', url.searchParams.get('bucket'), url.searchParams.get('path'))
        }
        if (url.protocol === 'gs:') return storageRef('gcs', url.hostname, decodeURIComponent(url.pathname))
        if (url.hostname === 'storage.googleapis.com') {
            const match = url.pathname.match(/^\/([^/]+)\/(.+)$/)
            return match ? storageRef('gcs', match[1], decodeURIComponent(match[2])) : null
        }
        if (url.hostname.endsWith('.storage.googleapis.com')) {
            return storageRef('gcs', url.hostname.slice(0, -'.storage.googleapis.com'.length), decodeURIComponent(url.pathname))
        }
        const match = url.pathname.match(/\/storage\/v1\/(?:object|render)\/(?:public|authenticated|sign)\/([^/]+)\/(.+)$/)
        if (!match) return null
        const bucket = decodeURIComponent(match[1])
        const path = decodeURIComponent(match[2])
        // Older topic records incorrectly wrapped a GCS bucket in a Supabase URL.
        const isLegacyGcs = [defaultGcsBucket, 'air-studio-prod'].includes(bucket) && /^topics\/\d+\//.test(path)
        return storageRef(isLegacyGcs ? 'gcs' : 'supabase', bucket, path)
    } catch {
        return null
    }
}

export function resolveGeneratedSceneStorage(scene: any, kind: 'image' | 'video', defaultGcsBucket: string): GeneratedSceneStorage | null {
    const metadata = scene?.metadata || {}
    const nested = metadata?.metadata || {}
    const cowork = metadata[`cowork_${kind}_asset`] || nested[`cowork_${kind}_asset`] || {}
    // Keep video-specific fields separate from generic image storage fields.
    const typedRecords = [metadata, nested].map(record => ({
        storage_provider: record[`${kind}_storage_provider`] || record.storage_provider,
        storage_bucket: record[`${kind}_storage_bucket`] || record.storage_bucket,
        storage_path: record[`${kind}_storage_path`] || record[`${kind}_storage_object_path`],
        gcs_bucket: record[`${kind}_gcs_bucket`],
        gcs_path: record[`${kind}_gcs_path`],
    }))
    const records = [cowork, ...typedRecords, ...(kind === 'image' ? [metadata, nested] : [])]
    // Explicit GCS references outrank stale legacy storage fields.
    for (const record of records) {
        const provider = text(record.storage_provider).toLowerCase()
        const path = record.gcs_path || (provider === 'gcs' ? record.object_path || record.storage_path || record.storage_object_path : '')
        const ref = storageRef('gcs', record.gcs_bucket || (provider === 'gcs' ? record.bucket || record.storage_bucket : '') || defaultGcsBucket, path)
        if (ref) return ref
    }
    const urls = [scene?.[`${kind}_url`], scene?.[kind], metadata[`${kind}_url`], metadata[kind], nested[`${kind}_url`], nested[kind]]
    const urlRefs = urls.map(value => sourceFromUrl(value, defaultGcsBucket)).filter(Boolean) as GeneratedSceneStorage[]
    const gcsUrlRef = urlRefs.find(ref => ref.provider === 'gcs')
    if (gcsUrlRef) return gcsUrlRef
    for (const record of records) {
        const provider = text(record.storage_provider).toLowerCase()
        if (provider && !['supabase', 'gcs'].includes(provider)) continue
        const bucket = record.bucket || record.storage_bucket
        const path = record.object_path || record.storage_path || record.storage_object_path
        const isLegacyGcs = !provider && [defaultGcsBucket, 'air-studio-prod'].includes(text(bucket)) && /^topics\/\d+\//.test(text(path).replace(/^\/+/, ''))
        const ref = storageRef(isLegacyGcs ? 'gcs' : 'supabase', bucket, path)
        if (ref) return ref
    }
    return urlRefs[0] || null
}
