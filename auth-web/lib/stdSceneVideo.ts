/** Worker output is a playable scene video, but still permits editorial camera motion. */
export function isWorkerSceneVideo(asset: any): boolean {
    const m = asset?.metadata || {}
    return asset?.asset_type === 'video' && Boolean(
        m.ae_mouth_fingerprint || m.lipsync_fingerprint || m.region_motion_plan_id
        || ['after_effects', 'region_motion'].includes(m.postprocess_mode),
    )
}

export function sceneVideoAssets(assets: any[], projectId: string) {
    const result = new Map<number, any>()
    for (const asset of [...(assets || [])].sort((a, b) => String(b.created_at || '').localeCompare(String(a.created_at || '')))) {
        if (asset.project_id !== projectId || asset.asset_type !== 'video' || !['uploaded', 'assigned'].includes(asset.status)) continue
        const number = Number(asset.scene_number)
        if (number > 0 && !result.has(number)) result.set(number, asset)
    }
    return result
}

export async function loadScenePreviewVideo(projectId: string, assetId: string, headers: Record<string, string>, signal: AbortSignal) {
    const response = await fetch(`/api/std/projects/${encodeURIComponent(projectId)}/assets/file?assetId=${encodeURIComponent(assetId)}&delivery=url`, { headers, signal })
    if (!response.ok) throw new Error(`Video loading failed (${response.status})`)
    if (response.headers.get('content-type')?.includes('application/json')) {
        const result = await response.json()
        if (!/^https?:\/\//i.test(result.url || '')) throw new Error('Invalid video playback URL')
        return { url: String(result.url), revoke: () => {} }
    }
    const blob = await response.blob()
    if (!blob.size || !blob.type.startsWith('video/')) throw new Error('Invalid video response')
    const url = URL.createObjectURL(blob)
    return { url, revoke: () => URL.revokeObjectURL(url) }
}

/** Scene-relative seeking keeps AIR output aligned when selecting or scrubbing a later subtitle. */
export function syncScenePreviewVideo(video: HTMLVideoElement, time: number, sceneStart: number, playing: boolean) {
    const offset = Math.max(0, time - sceneStart)
    const end = Number.isFinite(video.duration) && video.duration > 0 ? Math.max(0, video.duration - 0.04) : Infinity
    const target = Math.min(offset, end)
    if (video.readyState >= 1 && Math.abs(video.currentTime - target) > (playing ? 0.3 : 0.01)) video.currentTime = target
    if (!playing || offset >= end) video.pause()
    else if (video.paused) void video.play().catch(() => {})
}
