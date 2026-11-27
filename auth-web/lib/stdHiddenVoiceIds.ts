export function parseHiddenVoiceIds(value: unknown): string[] {
    try {
        const parsed = typeof value === 'string' ? JSON.parse(value || '[]') : value
        return Array.isArray(parsed) ? [...new Set(parsed.filter((id): id is string => typeof id === 'string' && Boolean(id.trim())).map(id => id.trim()))] : []
    } catch { return [] }
}

export function filterHiddenVoices<T extends { id?: unknown }>(voices: T[], hiddenIds: Iterable<string>): T[] {
    const hidden = new Set(hiddenIds)
    return voices.filter(voice => !hidden.has(String(voice.id || '')))
}
