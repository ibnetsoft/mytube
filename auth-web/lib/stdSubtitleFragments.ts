/** Closing punctuation belongs to the preceding subtitle, including old saved rows. */
export const isSubtitleClosingPunctuation = (text: string) => /^[\s。．.!！?？…，,、;；:：」』”’"'）)\]】]+$/u.test(text)

export function normalizeSubtitleFragments<T extends { text?: string; scene_number?: number;
    start_num?: number; end_num?: number; start_time?: string | number; end_time?: string | number;
    audio_regeneration_required?: boolean; [key: string]: any }>(
    subtitles: T[], maxChars = 20, options: { punctuationOnly?: boolean } = {},
): T[] {
    const withText = (item: T, text: string): T => ({
        ...item, text,
        ...(item.editor_speaker?.text === item.text ? {
            editor_speaker: { ...item.editor_speaker, text },
        } : {}),
    })
    // Quote splitting can strand the first kanji of the following narration:
    // ...頼ります」言 / い終えると... . Attach it FORWARD, never to the actor.
    // Restrict saved-row repair to generated quote fragments, not intentional
    // single-character dialogue, labels, or user-created subtitle splits.
    const repaired: T[] = []
    for (let i = 0; i < subtitles.length; i++) {
        const current = subtitles[i], next = subtitles[i + 1]
        const text = String(current.text || '').trim()
        const narration = (row: T) => row.dialogue_override !== true && row.dialogue_kind !== 'dialogue'
            && !row.dialogue_speaker && !row.editor_speaker?.name
        const end = Number(current.end_num ?? current.end_time ?? current.end)
        const start = Number(next?.start_num ?? next?.start_time ?? next?.start)
        if (next && /-quote-\d+$/.test(String(current.id || '')) && /^\p{Script=Han}$/u.test(text)
            && /^\p{Script=Hiragana}/u.test(String(next.text || '').trim())
            && Number(current.scene_number) === Number(next.scene_number) && narration(current) && narration(next)
            && (current.voice_id || null) === (next.voice_id || null)
            && (!Number.isFinite(end + start) || Math.abs(end - start) <= .05)) {
            const merged = withText(current, text + String(next.text || '').trimStart())
            for (const key of ['end_num', 'end_time', 'end']) if (next[key] !== undefined) (merged as any)[key] = next[key]
            for (const key of ['audio_url', 'tts_url', 'audio_asset_id', 'tts_asset_id', 'audio_duration']) {
                if (current[key] || next[key]) merged.audio_regeneration_required = true
                delete merged[key]
            }
            repaired.push(merged)
            i++
        } else repaired.push(current)
    }
    const result: T[] = []
    for (const source of repaired) {
        let item = { ...source }
        let text = String(item.text || '').trim()
        const previous = result[result.length - 1]
        const sameScene = previous && Number(previous.scene_number) === Number(item.scene_number)
        if (sameScene && text) {
            const prefix = text.match(/^[。．.!！?？…，,、;；:：」』”’）)\]】]+/u)?.[0] || ''
            const orphanCharacter = /^[\p{Script=Hiragana}\p{Script=Katakana}][。．.!！?？…，,、;；:：」』”’）)\]】]*$/u.test(text)
                && !/[。．.!！?？…」』”’]$/u.test(String(previous.text || ''))
                && (previous.dialogue_speaker || null) === (item.dialogue_speaker || null)
                && (previous.editor_speaker?.name || null) === (item.editor_speaker?.name || null)
                && (previous.voice_id || null) === (item.voice_id || null)
            const shortEnding = orphanCharacter || !options.punctuationOnly && Array.from(text).length <= 2 && /[\p{Script=Hiragana}\p{Script=Katakana}]/u.test(text)
                && !/[。．.!！?？…」』”’]$/u.test(String(previous.text || ''))
                && Array.from(String(previous.text || '') + text).length <= maxChars + 2
                && (previous.dialogue_speaker || null) === (item.dialogue_speaker || null)
                && (previous.voice_id || null) === (item.voice_id || null)
            const take = isSubtitleClosingPunctuation(text) || shortEnding ? text : prefix
            if (take) {
                const remaining = text.slice(take.length).trimStart()
                const start = Number(item.start_num ?? item.start_time)
                const end = Number(item.end_num ?? item.end_time)
                const boundary = remaining ? start + (end - start) * take.length / text.length : end
                const merged = withText(previous, String(previous.text || '').trimEnd() + take)
                if (Number.isFinite(boundary)) {
                    merged.end_num = boundary
                    merged.end_time = String(boundary)
                }
                if (shortEnding) {
                    merged.audio_regeneration_required = true
                    for (const key of ['audio_url', 'tts_url', 'audio_asset_id', 'tts_asset_id', 'audio_duration']) delete merged[key]
                }
                result[result.length - 1] = merged
                if (!remaining) continue
                item = withText(item, remaining)
                if (Number.isFinite(boundary)) {
                    item.start_num = boundary
                    item.start_time = String(boundary)
                }
                text = remaining
            }
        }
        if (text) result.push(item)
    }
    return result
}
