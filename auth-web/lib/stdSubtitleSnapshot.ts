import { normalizeSubtitleFragments } from './stdSubtitleFragments'

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
