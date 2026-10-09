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
    const response = await fetch(`/api/std/projects/${encodeURIComponent(projectId)}/assets/file?assetId=${encodeURIComponent(assetId)}`, { headers, signal })
    if (!response.ok) throw new Error(`Video loading failed (${response.status})`)
    const blob = await response.blob()
    if (!blob.size || !blob.type.startsWith('video/')) throw new Error('Invalid video response')
    const url = URL.createObjectURL(blob)
    return { url, revoke: () => URL.revokeObjectURL(url) }
}

/** Seek once, then let the decoder finish before issuing another seek. */
export function syncScenePreviewVideo(video: HTMLVideoElement, time: number, sceneStart: number, playing: boolean): boolean {
    const offset = Math.max(0, time - sceneStart)
    const end = Number.isFinite(video.duration) && video.duration > 0 ? Math.max(0, video.duration - 0.04) : Infinity
    video.loop = false
    const target = Math.min(offset, end)
    if (!playing) video.pause()
    // Repeated seeks while buffering can prevent any frame from being decoded.
    if (video.seeking || video.readyState < 2) return false
    if (Math.abs(video.currentTime - target) > (playing ? 0.5 : 0.01)) {
        video.currentTime = target
        if (video.seeking) return false
    }
    if (!playing || offset >= end) {
        video.pause()
        return true
    }
    if (video.readyState < 3) return false
    if (video.paused) void video.play().catch(() => {})
    return true
}

// Track intentional buffering pauses even if playback resumes before rejection arrives.
const narrationBufferPauses = new WeakMap<HTMLAudioElement, number>()

export async function playScenePreviewNarration(audio: HTMLAudioElement): Promise<void> {
    const pauseVersion = narrationBufferPauses.get(audio) || 0
    try {
        await audio.play()
    } catch (error) {
        if ((error as { name?: string })?.name === 'AbortError'
            && (narrationBufferPauses.get(audio) || 0) > pauseVersion) return
        throw error
    }
}

export type ScenePreviewBuffer = { audio: HTMLAudioElement | null }

/** The narration clock must wait for the selected clip, including scene transitions. */
export function syncScenePreviewPlayback(
    video: HTMLVideoElement | null, audio: HTMLAudioElement | null,
    time: number, sceneStart: number, playing: boolean, expectsVideo: boolean,
    buffer: ScenePreviewBuffer,
): boolean {
    const clockRunning = playing && Boolean(audio && (!audio.paused || buffer.audio === audio))
    const ready = video ? syncScenePreviewVideo(video, time, sceneStart, clockRunning) : !expectsVideo
    if (!playing) { buffer.audio = null; return false }
    const waiting = expectsVideo && !ready
    if (waiting) {
        video?.pause()
        if (audio && (!audio.paused || buffer.audio === audio)) {
            buffer.audio = audio
            narrationBufferPauses.set(audio, (narrationBufferPauses.get(audio) || 0) + 1)
            audio.pause()
        }
    } else if (buffer.audio) {
        const pausedAudio = buffer.audio
        buffer.audio = null
        // A scene load completing after Stop or a new playback session cannot restart old audio.
        if (pausedAudio === audio) void playScenePreviewNarration(audio).catch(() => {})
    }
    return waiting
}

/** Start a gentle zoom only after the original clip, across the remaining scene time. */
export function sceneClipTailStyle(time: number, sceneStart: number, sceneEnd: number, clipDuration: number) {
    const tailStart = sceneStart + clipDuration
    const hasTail = Number.isFinite(clipDuration) && clipDuration > 0 && sceneEnd > tailStart
    const progress = hasTail ? Math.max(0, Math.min(1, (time - tailStart) / (sceneEnd - tailStart))) : 0
    const eased = (1 - Math.cos(Math.PI * progress)) / 2
    // One third of the original scale change keeps zoom velocity at one third.
    return { transform: `scale(${1 + (0.06 / 3) * eased})`, transformOrigin: 'center', willChange: 'transform' }
}
