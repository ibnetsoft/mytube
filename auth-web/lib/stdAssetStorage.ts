// Legacy/TTS storage_path belongs to Supabase unless its provider says GCS.
export function assetStorageRef(metadata: any) {
    const m = metadata || {}
    const gcs = m.storage_provider === 'gcs' || (!m.storage_path && Boolean(m.gcs_path))
    return {
        provider: gcs ? 'gcs' : 'supabase',
        bucket: String(gcs ? (m.gcs_bucket || m.storage_bucket || '') : (m.storage_bucket || 'content-assets')),
        path: String(gcs ? (m.gcs_path || m.storage_path || '') : (m.storage_path || '')).replace(/^\/+/, ''),
    }
}
