// A preview, subtitle segment, or arbitrary upload cannot clear script invalidation.
export function completedScriptTtsProgress(progress: any, generatedText: string, scriptText: string) {
    const normalize = (text: string) => String(text || '').replace(/\s+/g, '')
    if (!normalize(scriptText) || normalize(generatedText) !== normalize(scriptText)) return { ...progress }
    const next = { ...progress, has_tts_audio: true, tts_completed: true, script_changed_requires_audio_regeneration: false }
    delete next.tts_invalidated_at
    delete next.tts_invalidated_reason
    return next
}
