export type DialoguePart = { text: string; dialogue: boolean; speaker?: string }
// Whitespace/quote removal is subtitle alignment only, never speech classification.
const ignored = (char: string) => /[\s"'“”‘’「」『』]/u.test(char)
export function mapDialogueAnnotations(subtitles: any[], annotations: any): Map<number, DialoguePart[]> {
    const result = new Map<number, DialoguePart[]>()
    if (annotations?.version !== 1 || annotations?.source !== 'codex-ai' || !Array.isArray(annotations.scenes)) return result
    for (const scene of annotations.scenes) {
        const rows = subtitles.map((s, i) => ({s, i})).filter(({s}) => Number(s.scene_number) === scene.scene_number)
        if (!rows.length || typeof scene.source_text !== 'string' || !Array.isArray(scene.spans)) continue
        const source = Array.from(scene.source_text as string)
        const compact = source.map((char, i) => ({char, i})).filter(({char}) => !ignored(char))
        const displayed = rows.flatMap(({s}) => Array.from(String(s.text || '')).filter(c => !ignored(c))).join('')
        if (compact.map(c => c.char).join('') !== displayed) continue // stale/edited script: no guessing
        const spans = scene.spans.filter((s: any) => s.status === 'confirmed' && s.speaker &&
            Number.isInteger(s.start) && Number.isInteger(s.end) && s.start >= 0 && s.end > s.start &&
            source.slice(s.start, s.end).join('') === s.text)
        let cursor = 0
        for (const {s, i} of rows) {
            const parts: DialoguePart[] = []
            for (const char of Array.from(String(s.text || ''))) {
                const position = compact[cursor]?.i
                const span = !ignored(char) && spans.find((a: any) => position >= a.start && position < a.end)
                if (!ignored(char)) cursor++
                const part = {text: char, dialogue: Boolean(span), speaker: span ? String(span.speaker) : undefined}
                const last = parts[parts.length - 1]
                if (last && last.dialogue === part.dialogue && last.speaker === part.speaker) last.text += char
                else parts.push(part)
            }
            result.set(i, parts)
        }
    }
    return result
}

/** Split only at AI-confirmed semantic boundaries; keep scene, media and total time. */
export function splitSubtitleDialogueBlocks(subtitles: any[], annotations: any): any[] {
    const mapped = mapDialogueAnnotations(subtitles, annotations)
    return subtitles.flatMap((subtitle, index) => {
        const parts = mapped.get(index)
        if (!parts) return [subtitle]
        const groups: DialoguePart[] = []
        let prefix = ''
        for (const part of parts) {
            const last = groups[groups.length - 1]
            if (Array.from(part.text).every(ignored)) {
                if (last) last.text += part.text
                else prefix += part.text
            } else if (last && last.dialogue === part.dialogue && last.speaker === part.speaker) {
                last.text += part.text
            } else {
                groups.push({...part, text: prefix + part.text})
                prefix = ''
            }
        }
        if (groups.length <= 1) return [subtitle]
        const start = Number(subtitle.start_num ?? subtitle.start_time)
        const end = Number(subtitle.end_num ?? subtitle.end_time)
        if (!Number.isFinite(start) || !Number.isFinite(end) || end <= start) return [subtitle]
        const weights = groups.map(g => Array.from(g.text).filter(c => !ignored(c)).length)
        const total = weights.reduce((a, b) => a + b, 0)
        let elapsed = 0
        return groups.map((group, i) => {
            const from = start + (end - start) * elapsed / total
            elapsed += weights[i]
            const to = i === groups.length - 1 ? end : start + (end - start) * elapsed / total
            const item = {...subtitle, id: `${subtitle.id || `sub-${index}`}-ai-${i + 1}`,
                text: group.text, start_num: from, end_num: to, start_time: String(from), end_time: String(to),
                dialogue_speaker: group.speaker || null, dialogue_kind: group.dialogue ? 'dialogue' : 'narration',
                dialogue_source: 'codex-ai', audio_regeneration_required: true}
            // An old audio clip includes the whole parent block, not this fragment.
            for (const key of ['audio_url', 'tts_url', 'audio_asset_id', 'tts_asset_id', 'audio_duration', 'dialogue_override']) delete item[key]
            return item
        })
    })
}
