export function subtitleWords(text: string): string[] {
    return String(text || '').match(/\S+/g) || []
}

export function sfxSubtitleIndex(cue: any, subtitles: any[]): number {
    if (cue.anchor_scope === 'scene') return sceneAnchor(cue, subtitles)?.index ?? -1
    if (cue.subtitle_id != null) return subtitles.findIndex(s => String(s.id) === String(cue.subtitle_id)
        && (!cue.subtitle_text || s.text === cue.subtitle_text))
    const index = Number(cue.subtitle_index)
    if (!cue.subtitle_text) return Number.isInteger(index) ? index : -1
    const matches = (s: any) => s?.text === cue.subtitle_text && String(s?.scene_number ?? '') === String(cue.scene_number ?? '')
    if (matches(subtitles[index])) return index
    const candidates = subtitles.flatMap((s, i) => matches(s) ? [i] : [])
    return candidates.length === 1 ? candidates[0] : -1
}

function sceneAnchor(cue: any, subtitles: any[]) {
    const compact = (text: string) => String(text || '').replace(/\s+/g, '')
    const matches = subtitles.flatMap((s, index) => String(s.scene_number) === String(cue.scene_number) ? [{ s, index }] : [])
    if (!matches.length || compact(matches.map(x => x.s.text).join('')) !== compact(cue.anchor_source_text)) return null
    let offset = Number(cue.anchor_offset) || 0
    for (const [position, { s, index }] of matches.entries()) {
        const length = compact(s.text).length
        if (offset < length || position === matches.length - 1) {
            let consumed = 0, boundary = 0
            for (const word of subtitleWords(s.text)) {
                if (consumed >= offset) break
                consumed += compact(word).length; boundary++
            }
            return { index, boundary }
        }
        offset -= length
    }
    return null
}

export function sfxNeedsReview(cue: any, subtitles: any[]): boolean {
    return cue.enabled !== false && cue.word_boundary != null && sfxSubtitleIndex(cue, subtitles) < 0
}

export function wordBoundaryTime(subtitle: any, boundary: number): number {
    const start = Number(subtitle.start_num ?? subtitle.start ?? subtitle.start_time) || 0
    const end = Number(subtitle.end_num ?? subtitle.end ?? subtitle.end_time) || start
    const count = subtitleWords(subtitle.text).length
    return start + Math.max(0, end - start) * Math.max(0, Math.min(count, boundary)) / Math.max(1, count)
}

export function resolveSfxCues(cues: any[], subtitles: any[]): any[] {
    const resolved = cues.flatMap(cue => {
        if (cue.enabled === false) return []
        if (cue.word_boundary == null) return [cue] // Existing timeline cues remain compatible.
        const index = sfxSubtitleIndex(cue, subtitles)
        if (index < 0 || !subtitles[index]) return [] // Deleted/merged anchor: never move to unrelated speech.
        const boundary = cue.anchor_scope === 'scene' ? sceneAnchor(cue, subtitles)!.boundary : cue.word_boundary
        const sub = subtitles[index]
        const words = sub.word_timestamps || sub.words
        const aligned = Array.isArray(words) ? Number(words[boundary]?.start) : NaN
        const automatic = cue.source === 'codex-sfx-v1' && !cue.user_override
        const start = Number.isFinite(aligned) ? aligned : automatic
            ? Number(sub.start_num ?? sub.start ?? sub.start_time) || 0 : wordBoundaryTime(sub, boundary)
        return [{ ...cue, subtitle_index: index, word_boundary: boundary, start,
            timing_mode: Number.isFinite(aligned) ? 'word' : automatic ? 'subtitle_start' : 'estimated_word' }]
    })
    const manual = resolved.filter(c => c.source !== 'codex-sfx-v1' || c.user_override)
    const accepted: any[] = [...manual]
    for (const cue of resolved.filter(c => c.source === 'codex-sfx-v1' && !c.user_override).sort((a,b) => a.start - b.start)) {
        if (accepted.every(c => Math.abs(Number(c.start) - cue.start) >= 5)) accepted.push(cue)
    }
    return accepted.sort((a,b) => Number(a.start) - Number(b.start))
}
