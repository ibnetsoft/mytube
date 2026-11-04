/** Wuxia voice rows are speech input, never the on-screen caption track. */
export function isWuxiaMovingtoon(project: any): boolean {
    const p = project?.project_payload || project || {}, s = p.structure || {}
    return s.wuxia_ae_package?.contract === 'wuxia_still_ae_episode/v1'
        || (s.image_style || p.image_style || s.effective_user_settings?.image_style) === 'wuxia_webtoon'
}
export function usesStandardSubtitles(project: any): boolean {
    if (isWuxiaMovingtoon(project)) return false
    const p = project?.project_payload || project || {}
    return (p.render_settings?.subtitles_enabled ?? p.structure?.render_settings?.subtitles_enabled) !== false
}
export function wuxiaSceneFrame(project: any, number: number, rows: any[], seconds: number) {
    const p = project?.project_payload || project || {}
    if (!isWuxiaMovingtoon(project)) return null
    const pkg = p.structure?.wuxia_ae_package || p.wuxia_ae_package
    const scene = pkg?.scenes?.find((s: any) => Number(String(s.scene_id).match(/S(\d+)$/)?.[1]) === number)
    if (!scene) return null
    const timing = rows.filter(r => Number(r.scene_number) === number)
    const start = Math.min(...timing.map(r => Number(r.start_num ?? r.start_time)))
    const end = Math.max(...timing.map(r => Number(r.end_num ?? r.end_time)))
    const fraction = Number.isFinite(start) && end > start ? Math.max(0, Math.min(.999999, (seconds - start) / (end - start))) : 0
    const state = scene.states?.find((s: any) => fraction >= s.start && fraction < s.end) || scene.states?.[0]
    const graphics = (scene.graphics || []).filter((g: any) => g.state_asset_id === state?.asset_id
        && fraction >= g.preview_start && fraction < g.preview_end)
    return { state, graphics, fraction, timingBasis: 'authored_preview_not_word_aligned_recording' }
}
