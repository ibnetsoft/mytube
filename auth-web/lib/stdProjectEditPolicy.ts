// Review-stage subtitle corrections are allowed; final decisions stay locked.
export function canEditStdProject(status: string, body: any): boolean {
    if (['approved', 'canceled'].includes(status)) return false
    if (status !== 'review_requested') return true
    const isRecord = (value: any) => value && typeof value === 'object' && !Array.isArray(value)
    if (!isRecord(body)) return false
    if (Object.keys(body).some(key => !['project_payload', 'progress_payload'].includes(key))) return false
    const payload = body.project_payload ?? {}
    const progress = body.progress_payload ?? {}
    if (!isRecord(payload) || !isRecord(progress)) return false
    return Array.isArray(payload.subtitles)
        && Object.keys(payload).every(key => ['subtitles', 'subtitles_saved', 'script', 'render_settings'].includes(key))
        && Object.keys(progress).every(key => ['subtitles_saved', 'subtitles_completed'].includes(key))
}
