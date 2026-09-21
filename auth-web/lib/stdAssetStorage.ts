// Always probe the primary Supabase copy before the GCS copy.
export function assetStorageRef(metadata: any) {
    const m = metadata || {}
    return {
        provider: 'supabase',
        bucket: String(m.supabase_bucket || (m.storage_provider !== 'gcs' ? m.storage_bucket : '') || 'content-assets'),
        path: String(m.supabase_path || m.storage_path || m.gcs_path || '').replace(/^\/+/, ''),
    }
}
