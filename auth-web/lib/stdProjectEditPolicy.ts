// Review-stage subtitle corrections are allowed; final decisions stay locked.
export function canEditStdProject(status: string, body: any): boolean {
    if (['approved', 'canceled'].includes(status)) return false
    if (status !== 'review_requested') return true
    const isRecord = (value: any) => value && typeof value === 'object' && !Array.isArray(value)
    if (!isRecord(body)) return false
    if (body.render_settings_scope === 'audio') {
        const payload = body.project_payload ?? {}
        const progress = body.progress_payload ?? {}
        return isRecord(payload) && isRecord(progress) && isRecord(payload.render_settings)
            && Object.keys(body).every(key => ['render_settings_scope', 'project_payload', 'progress_payload'].includes(key))
            && Object.keys(payload).every(key => ['render_settings', 'bgm_sfx_saved'].includes(key))
            && Object.keys(progress).every(key => key === 'bgm_sfx_saved')
    }
    if (body.render_settings_scope !== undefined && body.render_settings_scope !== 'subtitle') return false
    if (Object.keys(body).some(key => !['project_payload', 'progress_payload', 'render_settings_scope'].includes(key))) return false
    const payload = body.project_payload ?? {}
    const progress = body.progress_payload ?? {}
    if (!isRecord(payload) || !isRecord(progress)) return false
    return Array.isArray(payload.subtitles)
        && Object.keys(payload).every(key => ['subtitles', 'subtitles_saved', 'script', 'render_settings'].includes(key))
        && Object.keys(progress).every(key => ['subtitles_saved', 'subtitles_completed', 'subtitle_tts_completed', 'subtitle_tts_completed_at'].includes(key))
}
