export function stdRenderVersionOf(row: any): number {
    const value = Number(row?.metadata?.render_version ?? row?.render_version)
    return Number.isFinite(value) && value > 0 ? Math.floor(value) : 0
}

export function normalizeStdRenderHistory(rows: any[]) {
    const newestFirst = Array.isArray(rows) ? rows : []
    const chronological = [...newestFirst].reverse()
    const fallbackVersionById = new Map(chronological.map((row: any, index: number) => [row.id, index + 1]))
    return newestFirst.map((row: any) => ({
        ...row,
        render_version: stdRenderVersionOf(row) || fallbackVersionById.get(row.id) || 1,
    }))
}

export function attachStdRenderPlaybackAssets(rows: any[], assets: any[]) {
    const finalAssets = new Map<string, string>()
    for (const asset of assets) {
        const meta = asset.metadata || {}
        if (asset.asset_type === 'video' && ['uploaded', 'assigned'].includes(asset.status) && asset.id
            && meta.kind === 'motion_final' && meta.gcs_bucket && meta.gcs_path && meta.sha256) {
            finalAssets.set(JSON.stringify([meta.gcs_bucket, meta.gcs_path, meta.sha256]), asset.id)
        }
    }
    return rows.map(row => {
        const meta = row.metadata || {}
        const key = JSON.stringify([meta.gcs_bucket, meta.gcs_path, meta.sha256])
        return { ...row, playback_asset_id: row.status === 'completed' ? finalAssets.get(key) ?? null : null }
    })
}

export function nextStdRenderVersion(rows: any[]): number {
    return Math.max(0, ...normalizeStdRenderHistory(rows).map(stdRenderVersionOf)) + 1
}
