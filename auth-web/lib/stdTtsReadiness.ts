type ReadinessIssue = { index: number; reason: 'missing' | 'shared'; voice: string; narrationIndexes: number[] }
export function subtitleTtsReadiness(subtitles: any[], isDialogue: (row: any, index: number) => boolean, fallbackVoice: string) {
    const narration = new Map<string, number[]>()
    subtitles.forEach((row, index) => {
        if (isDialogue(row, index)) return
        const voice = String(row.voice_id || fallbackVoice || '').trim()
        if (voice) narration.set(voice, [...(narration.get(voice) || []), index])
    })
    const issues = subtitles.flatMap<ReadinessIssue>((row, index) => {
        if (!isDialogue(row, index)) return []
        const voice = String(row.voice_id || '').trim()
        if (!voice) return [{ index, reason: 'missing' as const, voice, narrationIndexes: [] as number[] }]
        const matches = narration.get(voice)
        return matches ? [{ index, reason: 'shared' as const, voice, narrationIndexes: matches }] : []
    })
    return { ready: subtitles.length > 0 && issues.length === 0, issues }
}
