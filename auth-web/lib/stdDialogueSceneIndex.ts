export function dialogueSceneIndex(subtitles: any[]) {
    const dialogue = subtitles.map((row, index) => ({ row, index })).filter(({row}) => row.dialogue_kind === 'dialogue')
    const sceneNumbers = [...new Set(dialogue.map(({row}) => Number(row.scene_number)).filter(n => n > 0))].sort((a,b) => a-b)
    return { version: 1, scene_numbers: sceneNumbers, scene_count: sceneNumbers.length, subtitle_count: dialogue.length,
        scenes: sceneNumbers.map(number => ({ scene_number: number, subtitle_indices: dialogue.filter(({row}) => Number(row.scene_number) === number).map(({index}) => index),
            speakers: [...new Set(dialogue.filter(({row}) => Number(row.scene_number) === number).map(({row}) => String(row.dialogue_speaker || row.speaker?.name || '').trim()).filter(Boolean))] })) }
}
