import { scanDialogueQuoteState } from './stdDialogueQuoteState'
function dialogueSubtitleIndexes(subtitles: any[], parts: Map<number, any[]>) {
    return subtitles.flatMap((row, index) => {
        if (row.dialogue_override === false) return []
        const annotated = parts.get(index)?.some(part => part.dialogue)
        const inferred = typeof row.dialogue_override === 'boolean' ? row.dialogue_override
            : Boolean(annotated || row.dialogue_speaker || row.editor_speaker?.name || scanDialogueQuoteState(row.text).isDialogue)
        return annotated || inferred ? [index] : []
    })
}
export function missingSpeakerSubtitleIndexes(subtitles: any[], parts: Map<number, any[]>, speakers: any[]) {
    return dialogueSubtitleIndexes(subtitles, parts).filter(index => !speakers[index]?.name)
}
export function subtitleSpeakerProgress(subtitles: any[], parts: Map<number, any[]>, speakers: any[]) {
    const indexes = dialogueSubtitleIndexes(subtitles, parts)
    return { total: indexes.length, confirmed: indexes.filter(index => speakers[index]?.name).length }
}
export function subtitleSpeechChanged(before: any[], after: any[]) {
    const input = (rows: any[]) => rows.map(row => [row.text, row.voice_id, row.dialogue_kind,
        row.dialogue_override, row.dialogue_speaker, row.editor_speaker?.name, row.editor_speaker?.text])
    return JSON.stringify(input(before)) !== JSON.stringify(input(after))
}
