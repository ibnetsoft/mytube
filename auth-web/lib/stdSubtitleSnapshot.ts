import { normalizeSubtitleFragments } from './stdSubtitleFragments'
import { splitTextToSingleLineChunks } from './stdSubtitles'

function splitUntouchedRecoveryRow(row: any, maxChars: number): any[] {
    if (!/^sub-\d+-source-recovery$/.test(String(row?.id || ''))
        || row?.restored_audio_pending !== true || row?.voice_assignment_pending !== true
        || row?.voice_id || row?.voice_name || row?.editor_speaker || row?.dialogue_speaker
        || row?.dialogue_override != null || row?.audio_url || row?.tts_url || row?.audio_asset_id || row?.tts_asset_id) return [row]
    const original = String(row.text || '')
    const chunks = splitTextToSingleLineChunks(original, maxChars)
    // Never rewrite whitespace or punctuation to make an automatic repair fit.
    if (chunks.length < 2 || chunks.join('') !== original) return [row]
    const start = Number(row.start_num ?? row.start_time ?? row.start)
    const end = Number(row.end_num ?? row.end_time ?? row.end)
    if (!Number.isFinite(start) || !Number.isFinite(end) || end < start) return [row]
    const lengths = chunks.map(chunk => Array.from(chunk).length)
    const total = lengths.reduce((sum, length) => sum + length, 0)
    let elapsed = 0
    return chunks.map((text, index) => {
        const from = index === 0 ? start : start + (end - start) * elapsed / total
        elapsed += lengths[index]
        const to = index === chunks.length - 1 ? end : start + (end - start) * elapsed / total
        return { ...row, id: `${row.id}-block-${index + 1}`, text,
            start_num: from, end_num: to, start_time: String(from), end_time: String(to),
            ...(row.start !== undefined ? { start: from } : {}), ...(row.end !== undefined ? { end: to } : {}) }
    })
}

/**
 * Saved editor rows are authoritative. Missing scenes, changed wording, custom
 * timing and manual splits are valid edits, not reasons to regenerate a draft.
 * Script replacement/regeneration must explicitly supply its new subtitle rows.
 */
export function restoreSavedSubtitleSnapshot(
    savedSubtitles: unknown,
    generateInitialSubtitles: () => any[],
    maxChars = 20,
): any[] {
    if (!Array.isArray(savedSubtitles) || savedSubtitles.length === 0) return generateInitialSubtitles()
    // Repair old punctuation-only rows without re-splitting dialogue, merging
    // short spoken words, clearing voices, or replacing recorded timings.
    return normalizeSubtitleFragments(savedSubtitles, maxChars, { punctuationOnly: true })
}

/** Repair only untouched generated placeholders that still equal their source scene. */
export function splitSourceRecoveryPlaceholders(rows: any[], scenes: any[], maxChars = 20): any[] {
    const textByScene = new Map((scenes || []).map(scene => [Number(scene?.scene_number ?? scene?.scene_order),
        String(scene?.scene_text || scene?.script_excerpt || scene?.narration || '').trim()]))
    return rows.flatMap(row => textByScene.get(Number(row?.scene_number)) === String(row?.text || '')
        ? splitUntouchedRecoveryRow(row, maxChars) : [row])
}
