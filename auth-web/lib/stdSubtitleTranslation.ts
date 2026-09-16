export type SubtitleTranslationBlock = {
    index: number
    source_text: string
    translated_text: string
}

export const SUBTITLE_TRANSLATION_LANGUAGES = {
    en: 'English',
    vi: 'Vietnamese',
    th: 'Thai',
} as const

export type SubtitleTranslationLanguage = keyof typeof SUBTITLE_TRANSLATION_LANGUAGES

export function isSubtitleTranslationLanguage(value: unknown): value is SubtitleTranslationLanguage {
    return Object.prototype.hasOwnProperty.call(SUBTITLE_TRANSLATION_LANGUAGES, String(value || ''))
}

export function subtitleTranslationKey(index: number, sourceText: string): string {
    return `${Math.floor(Number(index))}\u0000${String(sourceText || '')}`
}

export function translationMapFromBlocks(blocks: unknown): Record<string, string> {
    const result: Record<string, string> = {}
    if (!Array.isArray(blocks)) return result
    for (const block of blocks) {
        const index = Number(block?.index)
        const sourceText = String(block?.source_text || '')
        const translatedText = String(block?.translated_text || '').trim()
        if (!Number.isInteger(index) || index < 0 || !sourceText || !translatedText) continue
        result[subtitleTranslationKey(index, sourceText)] = translatedText
    }
    return result
}

export function parseStrictTranslationResponse(
    raw: string,
    sourceBlocks: Array<{ id: string; text: string }>,
): Array<{ id: string; translation: string }> {
    const cleaned = String(raw || '').trim().replace(/^```(?:json)?\s*/i, '').replace(/\s*```$/, '')
    const parsed = JSON.parse(cleaned)
    const translations = Array.isArray(parsed) ? parsed : parsed?.translations
    if (!Array.isArray(translations)) throw new Error('Translation response is not an array')

    const byId = new Map<string, string>()
    for (const item of translations) {
        const id = String(item?.id || '')
        const translation = String(item?.translation || '').trim()
        if (!id || !translation || byId.has(id)) continue
        byId.set(id, translation)
    }

    const result = sourceBlocks.map(block => ({ id: block.id, translation: byId.get(block.id) || '' }))
    if (result.some(item => !item.translation) || byId.size !== sourceBlocks.length) {
        throw new Error('Translation response did not preserve every subtitle block')
    }
    return result
}

export function buildSubtitleTranslationPrompt(
    blocks: Array<{ id: string; text: string }>,
    targetLanguage: SubtitleTranslationLanguage,
): string {
    const languageName = SUBTITLE_TRANSLATION_LANGUAGES[targetLanguage]
    return `You are translating Korean video subtitle blocks into ${languageName} for a human dialogue reviewer.

Translate each block independently and faithfully. The reviewer must be able to tell whether the text is character dialogue or narration.

Strict rules:
1. Return exactly one translation for every input id, in the same order.
2. Never merge, split, summarize, omit, or move content between blocks.
3. Preserve direct speech as direct speech. Preserve quotation marks, speaker labels, sentence boundaries, tone, and emotional cues.
4. Do not turn narration into dialogue or dialogue into narration.
5. Translate the complete text of each block into natural ${languageName}. Do not classify the block and do not add explanations.
6. Return only valid JSON in this shape: {"translations":[{"id":"b0","translation":"..."}]}

Input blocks:
${JSON.stringify(blocks)}`
}

// Match unchanged blocks in sequence, consuming each saved occurrence once.
// Indexes are positions, not identities: merging a block shifts the entire suffix.
export function remapSubtitleTranslations(
    saved: SubtitleTranslationBlock[],
    current: Array<{ index: number; source_text: string }>,
): SubtitleTranslationBlock[] {
    const old = [...saved].sort((a, b) => a.index - b.index)
    const lengths = Array.from({ length: old.length + 1 }, () => new Uint16Array(current.length + 1))
    for (let i = old.length - 1; i >= 0; i--) {
        for (let j = current.length - 1; j >= 0; j--) {
            lengths[i][j] = old[i].source_text === current[j].source_text
                ? 1 + lengths[i + 1][j + 1]
                : Math.max(lengths[i + 1][j], lengths[i][j + 1])
        }
    }
    const result: SubtitleTranslationBlock[] = []
    let i = 0, j = 0
    while (i < old.length && j < current.length) {
        if (old[i].source_text === current[j].source_text) {
            result.push({ ...current[j], translated_text: old[i].translated_text })
            i++; j++
        } else if (lengths[i + 1][j] >= lengths[i][j + 1]) i++
        else j++
    }
    return result
}

export function remapSubtitleTranslationMap(
    saved: Record<string, string>,
    subtitles: Array<{ text?: string }>,
): Record<string, string> {
    const blocks = Object.entries(saved).map(([key, translated_text]) => {
        const separator = key.indexOf('\u0000')
        return { index: Number(key.slice(0, separator)), source_text: key.slice(separator + 1), translated_text }
    })
    return translationMapFromBlocks(remapSubtitleTranslations(blocks,
        subtitles.map((subtitle, index) => ({ index, source_text: String(subtitle.text || '').trim() }))))
}
