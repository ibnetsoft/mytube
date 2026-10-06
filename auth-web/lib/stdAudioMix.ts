export function audioAssetRole(asset: any): string {
    const type = String(asset?.asset_type || '')
    const role = String(asset?.metadata?.audio_role || '')
    return type === 'other' && ['bgm', 'sfx'].includes(role) ? role : type
}

// Older production schemas support `other`, but not dedicated BGM/SFX types.
export function audioAssetStorageFields(role: string) {
    return ['bgm', 'sfx'].includes(role)
        ? { asset_type: 'other', metadata: { audio_role: role } }
        : { asset_type: role, metadata: {} }
}

export function backgroundVolume(value: unknown): number {
    const volume = value == null ? 0.08 : Number(value)
    return Number.isFinite(volume) ? Math.max(0, Math.min(1, volume)) : 0.08
}


export function backgroundWindow(settings: any, subtitles: any[], duration: number) {
    const from = Number(settings.bgm_start_scene) || 0
    const to = Number(settings.bgm_end_scene) || 0
    const time = (row: any, end: boolean) => Number(end ? (row.end_num ?? row.end_time ?? row.end) : (row.start_num ?? row.start_time ?? row.start))
    // Subtitle numbers are one-based within the chosen scene, matching the editor.
    const sceneSubtitles = subtitles.filter(row => Number(row.scene_number) === from)
    const subtitleNumber = Number(settings.bgm_start_subtitle ?? 1)
    const selectedSubtitle = Number.isInteger(subtitleNumber) && subtitleNumber > 0 ? sceneSubtitles[subtitleNumber - 1] : undefined
    const subtitleStart = selectedSubtitle ? time(selectedSubtitle, false) : NaN
    const ends = subtitles.filter(row => Number(row.scene_number) === to).map(row => time(row, true)).filter(Number.isFinite)
    const valid = (!from || Number.isFinite(subtitleStart)) && (!to || ends.length > 0) && (!from || !to || from <= to)
    const start = from ? (Number.isFinite(subtitleStart) ? subtitleStart : 0) : 0
    const end = to ? (ends.length ? Math.max(...ends) : 0) : duration
    const length = Math.max(0, end - start)
    const fade = (value: unknown) => Math.min(length / 2, Math.max(0, Math.min(30, Number(value ?? 2) || 0)))
    return { start, end, valid: valid && end > start, fadeIn: fade(settings.bgm_fade_in), fadeOut: fade(settings.bgm_fade_out) }
}

// A one-shot track can finish before its selected scene range. Fade toward the
// audible end, while looping tracks continue to use the full selected range.
export function backgroundPlaybackWindow(window: ReturnType<typeof backgroundWindow>, sourceDuration: number, loop: boolean) {
    if (loop || !Number.isFinite(sourceDuration) || sourceDuration <= 0) return window
    const end = Math.min(window.end, window.start + sourceDuration)
    const length = Math.max(0, end - window.start)
    return { ...window, end, valid: window.valid && length > 0,
        fadeIn: Math.min(window.fadeIn, length / 2), fadeOut: Math.min(window.fadeOut, length / 2) }
}

export function backgroundEnvelope(time: number, window: ReturnType<typeof backgroundWindow>) {
    if (!window.valid || time < window.start || time >= window.end) return 0
    return Math.min(1, window.fadeIn > 0 ? (time - window.start) / window.fadeIn : 1,
        window.fadeOut > 0 ? (window.end - time) / window.fadeOut : 1)
}

// Draw the audible envelope, not just the unmodified file. For loops, display
// the current pass so the last pass shows the fade toward the selected end.
export function backgroundWaveformPeaks(peaks: number[], duration: number, window: ReturnType<typeof backgroundWindow>, time: number, loop: boolean) {
    if (!(duration > 0) || !Number.isFinite(duration)) return []
    const range = backgroundPlaybackWindow(window, duration, loop)
    const elapsed = Math.max(0, Math.min(time, range.end - 0.000001) - range.start)
    const cycleStart = loop ? Math.floor(elapsed / duration) * duration : 0
    return peaks.map((peak, index) => peak * backgroundEnvelope(
        range.start + cycleStart + index / Math.max(1, peaks.length - 1) * duration, range))
}
