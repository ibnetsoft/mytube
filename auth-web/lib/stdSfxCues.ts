export function subtitleWords(text: string): string[] {
    return String(text || '').match(/\S+/g) || []
}

export function sfxSubtitleIndex(cue: any, subtitles: any[]): number {
    if (cue.subtitle_id != null) return subtitles.findIndex(s => String(s.id) === String(cue.subtitle_id))
    const index = Number(cue.subtitle_index)
    if (!cue.subtitle_text) return Number.isInteger(index) ? index : -1
    const matches = (s: any) => s?.text === cue.subtitle_text && String(s?.scene_number ?? '') === String(cue.scene_number ?? '')
    if (matches(subtitles[index])) return index
    const candidates = subtitles.flatMap((s, i) => matches(s) ? [i] : [])
    return candidates.length === 1 ? candidates[0] : -1
}

export function wordBoundaryTime(subtitle: any, boundary: number): number {
    const start = Number(subtitle.start_num ?? subtitle.start ?? subtitle.start_time) || 0
    const end = Number(subtitle.end_num ?? subtitle.end ?? subtitle.end_time) || start
    const count = subtitleWords(subtitle.text).length
    return start + Math.max(0, end - start) * Math.max(0, Math.min(count, boundary)) / Math.max(1, count)
}

export function resolveSfxCues(cues: any[], subtitles: any[]): any[] {
    return cues.flatMap(cue => {
        if (cue.enabled === false) return []
        if (cue.word_boundary == null) return [cue] // Existing timeline cues remain compatible.
        const index = sfxSubtitleIndex(cue, subtitles)
        if (index < 0 || !subtitles[index]) return [] // Deleted/merged anchor: never move to unrelated speech.
        return [{ ...cue, subtitle_index: index, start: wordBoundaryTime(subtitles[index], cue.word_boundary) }]
    })
}
