export const V4_VOCAL_TAGS = ['whispers', 'shouts', 'curious', 'excited', 'crying', 'sighs', 'laughs', 'sarcastic', 'soft voice', 'calm voice'] as const
type Cue = { offset: number; tag: string }
export type VoicePerformance = { version: 1; text: string; cues: Cue[] }

export function normalizeVoicePerformance(value: any, text: string): VoicePerformance | undefined {
    if (value == null) return undefined
    if (value.version !== 1 || value.text !== text || !Array.isArray(value.cues) || value.cues.length > 16) {
        throw new Error('연기 지시가 현재 대본과 일치하지 않습니다. 새 대본의 연기 지시를 확인해 주세요.')
    }
    const size = Array.from(text).length, seen = new Set<number>()
    const cues = value.cues.map((cue: any) => {
        if (!Number.isInteger(cue.offset) || cue.offset < 0 || cue.offset >= size || seen.has(cue.offset)
            || !V4_VOCAL_TAGS.includes(cue.tag)) throw new Error('유효하지 않은 v4 연기 태그입니다.')
        seen.add(cue.offset)
        return { offset: cue.offset as number, tag: cue.tag as string }
    }).sort((a: Cue, b: Cue) => a.offset - b.offset)
    return cues.length ? { version: 1, text, cues } : undefined
}

export function voicePerformanceKey(value: VoicePerformance | undefined): string {
    return value ? JSON.stringify(value) : ''
}

/** Pure display text stays untouched. Only validated, matching NEW-script plans apply. */
export function mapVoicePerformance(rows: any[], plan: any): Array<VoicePerformance | undefined> {
    const result: Array<VoicePerformance | undefined> = rows.map(() => undefined)
    if (plan?.version !== 1 || plan?.source !== 'codex-ai' || plan?.model !== 'eleven_v4'
        || plan?.offset_unit !== 'unicode-codepoint' || !Array.isArray(plan.scenes)) return result
    const ignored = (c: string) => /[\s"'“”‘’「」『』]/u.test(c)
    for (const scene of plan.scenes) {
        if (typeof scene.source_text !== 'string' || !Array.isArray(scene.cues)) continue
        const group = rows.map((row, index) => ({ row, index })).filter(({ row }) => Number(row.scene_number) === scene.scene_number)
        const source = Array.from(scene.source_text as string).map((c, i) => ({ c, i })).filter(({ c }) => !ignored(c))
        const chars = group.flatMap(({ row, index }) => Array.from(String(row.text || '')).map((c, offset) => ({ c, offset, index })).filter(({ c }) => !ignored(c)))
        if (source.map(x => x.c).join('') !== chars.map(x => x.c).join('')) continue
        const mapped = scene.cues.map((cue: any) => ({ ...cue, position: source.findIndex(x => x.i >= cue.offset) }))
        for (const { row, index } of group) {
            const start = chars.findIndex(c => c.index === index)
            if (start < 0) continue
            const cues: Cue[] = []
            // Independent subtitle recordings need the current delivery at their start.
            const active = mapped.filter((c: any) => c.position >= 0 && c.position <= start && !['sighs', 'laughs'].includes(c.tag)).at(-1)
            if (active) cues.push({ offset: 0, tag: active.tag })
            for (const cue of mapped) {
                const at = chars[cue.position]
                if (at?.index !== index) continue
                const offset = cue.position === start ? 0 : at.offset
                const same = cues.findIndex(c => c.offset === offset)
                if (same >= 0) cues.splice(same, 1)
                cues.push({ offset, tag: cue.tag })
            }
            try { result[index] = normalizeVoicePerformance({ version: 1, text: String(row.text || '').trim(), cues }, String(row.text || '').trim()) }
            catch { /* Never attach invalid or stale stage output to a recording. */ }
        }
    }
    return result
}

/** Project Unicode offsets onto plain chunks before adding tags; never split a tag. */
export function performanceTextForChunk(source: string, chunk: string, from: number, performance?: VoicePerformance): string {
    if (!performance) return chunk
    const start = source.indexOf(chunk, from)
    if (start < 0) throw new Error('TTS 구간을 원문에 맞출 수 없습니다.')
    const before = Array.from(source.slice(0, start)).length, chars = Array.from(chunk)
    const cues = performance.cues.filter(c => c.offset >= before && c.offset < before + chars.length)
    const active = performance.cues.filter(c => c.offset < before && !['sighs', 'laughs'].includes(c.tag)).at(-1)
    if (active && !cues.some(c => c.offset === before)) cues.unshift({ offset: before, tag: active.tag })
    for (const cue of cues.slice().sort((a, b) => b.offset - a.offset)) chars.splice(cue.offset - before, 0, `[${cue.tag}] `)
    return chars.join('')
}

export function elevenLabsVoiceSettings(model: string, input: { stability?: number; similarityBoost?: number; style?: number; speed?: number }) {
    const settings: Record<string, number> = {}
    if (Number.isFinite(input.stability)) settings.stability = Number(input.stability)
    if (Number.isFinite(input.similarityBoost)) settings.similarity_boost = Number(input.similarityBoost)
    if (model !== 'eleven_v4') {
        if (Number.isFinite(input.style)) settings.style = Number(input.style)
        if (Number.isFinite(input.speed)) settings.speed = Math.min(1.2, Math.max(0.7, Number(input.speed)))
    }
    return settings
}
