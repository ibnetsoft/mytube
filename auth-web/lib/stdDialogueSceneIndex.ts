// A text-matched user attribution is authoritative over legacy voice-ID fallbacks.
export function subtitleDialogueSpeakerName(row: any): string {
    const manual = row.editor_speaker
    return String((manual?.text === row.text && manual?.name) || row.dialogue_speaker || row.speaker?.name || '').trim()
}

export function dialogueSceneIndex(subtitles: any[]) {
    const dialogue = subtitles.map((row, index) => ({ row, index })).filter(({row}) => row.dialogue_kind === 'dialogue')
    const sceneNumbers = [...new Set(dialogue.map(({row}) => Number(row.scene_number)).filter(n => n > 0))].sort((a,b) => a-b)
    return { version: 1, scene_numbers: sceneNumbers, scene_count: sceneNumbers.length, subtitle_count: dialogue.length,
        scenes: sceneNumbers.map(number => ({ scene_number: number, subtitle_indices: dialogue.filter(({row}) => Number(row.scene_number) === number).map(({index}) => index),
            speakers: [...new Set(dialogue.filter(({row}) => Number(row.scene_number) === number).map(({row}) => subtitleDialogueSpeakerName(row)).filter(Boolean))] })) }
}
