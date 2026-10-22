/** Explicit whole-row attribution overrides AI fragments in the editor, too. */
export function subtitleDialogueDisplayParts(subtitle: any, parts: any[] | undefined, dialogue: boolean, speaker: string) {
    if (typeof subtitle.dialogue_override === 'boolean') {
        return [{ text: subtitle.text, dialogue: subtitle.dialogue_override, speaker }]
    }
    if (parts?.some(part => part.dialogue)) return parts
    return [{ text: subtitle.text, dialogue, speaker }]
}

/** A narration switch changes one row; recorded text and timeline stay intact. */
export function assignSubtitleNarration(subtitles: any[], target: number, defaultVoiceId: string,
    voiceNames: Map<string, string>, isNarration: (row: any, index: number) => boolean) {
    const row = subtitles[target]
    if (!row) return subtitles
    const donor = subtitles.map((item, index) => ({ item, index }))
        .filter(({ item, index }) => index !== target && Number(item.scene_number) === Number(row.scene_number)
            && item.voice_id && isNarration(item, index))
        .sort((a, b) => Math.abs(a.index - target) - Math.abs(b.index - target))[0]?.item
    const voiceId = String(donor?.voice_id || defaultVoiceId || '')
    return subtitles.map((item, index) => index !== target ? item : {
        ...item, dialogue_override: false, dialogue_kind: 'narration', dialogue_source: 'user',
        dialogue_speaker: null, editor_speaker: null,
        ...(voiceId ? { voice_id: voiceId, voice_name: donor?.voice_name || voiceNames.get(voiceId) || voiceId,
            voice_direction: donor?.voice_direction || '' } : {}),
    })
}
