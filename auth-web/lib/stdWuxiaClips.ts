import reviewedPrompts from './wuxiaStateClipPrompts.json'
/** Source-bound, optional footage inside an existing still-state window. */
export const WUXIA_CLIP = 'wuxia_state_clip/v1'
export function wuxiaClipStates(project: any, sceneNumber?: number): any[] {
    const payload = project?.project_payload || project || {}
    return (payload.structure?.wuxia_ae_package?.scenes || []).flatMap((scene: any) => {
        const number = Number(String(scene.scene_id).match(/S(\d+)$/)?.[1])
        return sceneNumber && number !== sceneNumber ? [] : (scene.states || []).map((state: any) => ({ ...state, scene_number: number }))
    })
}
export function validWuxiaClip(clip: any): boolean {
    const finite = (v: any) => typeof v === 'number' && Number.isFinite(v)
    return clip?.contract === WUXIA_CLIP && /^[a-f0-9]{64}$/.test(clip.sha256 || '')
        && /^[a-f0-9]{64}$/.test(clip.source_state_sha256 || '') && !!clip.asset_id
        && typeof clip.gcs_bucket === 'string' && !!clip.gcs_bucket
        && typeof clip.gcs_path === 'string' && !!clip.gcs_path && !clip.gcs_path.split('/').includes('..')
        && Number.isInteger(clip.width) && Number.isInteger(clip.height) && clip.width >= 640 && clip.height >= 360
        && clip.width * clip.height <= 16_000_000 && Math.abs(clip.width / clip.height - 16 / 9) < .01
        && finite(clip.duration_seconds) && clip.duration_seconds > 0 && clip.duration_seconds <= 30
        && finite(clip.source_in_seconds) && clip.source_in_seconds >= 0
        && finite(clip.play_seconds) && clip.play_seconds > 0
        && clip.source_in_seconds + clip.play_seconds <= clip.duration_seconds + 1e-6
        && finite(clip.start_offset_seconds) && clip.start_offset_seconds >= 0
}
export function withWuxiaStateClips(project: any, assets: any[]) {
    const states = new Map(wuxiaClipStates(project).map(s => [s.asset_id, s]))
    const clips: Record<string, any> = {}, issues: string[] = [], restoreIds: Record<string,string> = {}, seen = new Set<string>()
    for (const asset of [...assets].filter(a => a.metadata?.kind === 'wuxia_state_clip' && a.metadata?.ready === true)
        .sort((a, b) => String(b.created_at).localeCompare(String(a.created_at)) || String(b.id).localeCompare(String(a.id)))) {
        const clip = asset.metadata.clip, state = states.get(clip?.state_asset_id)
        if (!state || seen.has(state.asset_id)) continue
        seen.add(state.asset_id) // A disabled latest attachment must not resurrect older footage.
        if (!['uploaded', 'assigned'].includes(asset.status) || asset.metadata.enabled === false) continue
        restoreIds[state.asset_id] = asset.id
        if (state.sha256 !== clip.source_state_sha256 || !validWuxiaClip(clip)) { issues.push(`${state.asset_id}: 원화 또는 영상 연결이 달라졌습니다. 원화로 복원하거나 다시 업로드해 주세요.`); continue }
        clips[state.asset_id] = { ...clip, media_url: `/api/std/projects/${encodeURIComponent(project.id)}/assets/file?assetId=${encodeURIComponent(asset.id)}` }
    }
    return { ...project, project_payload: { ...project.project_payload, wuxia_state_clips: clips, wuxia_state_clip_issues: issues, wuxia_state_clip_restore_ids: restoreIds } }
}
export function wuxiaStateClipFrame(project: any, state: any, seconds: number, start: number, end: number, fps: number) {
    const clip = (project?.project_payload || project)?.wuxia_state_clips?.[state?.asset_id]
    if (!clip) return null
    if (!validWuxiaClip(clip) || clip.source_state_sha256 !== state.sha256) throw Error('영상과 원화의 연결이 달라졌습니다.')
    const from = Number(state.start || 0) * (end - start) + clip.start_offset_seconds
    const until = Number(state.end ?? 1) * (end - start)
    if (from + clip.play_seconds > until + 1e-6) throw Error('영상 사용 길이가 상태 컷 구간보다 깁니다. 사용 구간을 줄여 주세요.')
    const local = Math.floor(Math.max(0, seconds - start) * fps + 1e-7) / fps
    if (local < from - 1e-7 || local >= from + clip.play_seconds - 1e-7) return null
    return { clip, source_seconds: clip.source_in_seconds + local - from }
}
export function wuxiaClipPrompt(state: any): string {
    const reviewed=(reviewedPrompts as Record<string, {prompt:string}>)[state?.sha256]
    if(reviewed)return reviewed.prompt
    return `Create a single image-to-video shot using ONLY the attached original state artwork as the visual reference. Preserve the exact character faces, anatomy, outfits, injuries, weapon shape and ownership, setting, framing and lighting. 16:9. Fixed camera; no zoom. Animate only the action already supported by this image: ${String(state.description || 'a restrained continuation of the depicted moment')}. One clear action, then settle naturally. Do not introduce another character, new object, next scene, camera transition, text, lettering, speech bubbles or subtitles. No dialogue, narration, music or audio. Do not duplicate or morph hands, weapons or faces. Do not add impact flashes or debris before actual contact. Keep motion small enough to remain consistent with the following still. Deliver a short clip; the editor will use the explicitly selected source interval at normal speed.`
}
