import { scanDialogueQuoteState } from './stdDialogueQuoteState'
export function subtitleSpeakerProgress(subtitles: any[], parts: Map<number, any[]>, speakers: any[]) {
    return subtitles.reduce((count, row, index) => {
        const annotated = parts.get(index)?.some(part => part.dialogue)
        const inferred = typeof row.dialogue_override === 'boolean' ? row.dialogue_override
            : Boolean(annotated || row.dialogue_speaker || row.editor_speaker?.name || scanDialogueQuoteState(row.text).isDialogue)
        if (!annotated && !inferred) return count
        return { total: count.total + 1, confirmed: count.confirmed + (speakers[index]?.name ? 1 : 0) }
    }, { total: 0, confirmed: 0 })
}
export function subtitleSpeechChanged(before: any[], after: any[]) {
    const input = (rows: any[]) => rows.map(row => [row.text, row.voice_id, row.dialogue_kind,
        row.dialogue_override, row.dialogue_speaker, row.editor_speaker?.name, row.editor_speaker?.text])
    return JSON.stringify(input(before)) !== JSON.stringify(input(after))
}
