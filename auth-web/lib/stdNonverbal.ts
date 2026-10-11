export const NONVERBAL_MODE = 'nonverbal_preschool'
export const NONVERBAL_CONTRACT = 'nonverbal_preschool/v1'
export function nonverbalStructure(value: any): any {
    return value?.pregenerated_structure || value?.structure || value?.project_payload?.structure || value?.source_payload?.pregenerated_structure || {}
}
export function isNonverbalProject(value: any): boolean {
    return [value?.production_mode, value?.project_payload?.production_mode, nonverbalStructure(value)?.production_mode].includes(NONVERBAL_MODE)
}
export function hasReadyNonverbalPlan(value: any): boolean {
    const structure = nonverbalStructure(value)
    const scenes = structure?.scenes
    if (!isNonverbalProject(value) || structure.nonverbal_contract !== NONVERBAL_CONTRACT
        || structure.nonverbal_plan_status !== 'ready' || structure.speech_enabled !== false
        || structure.subtitles_enabled !== false || !Array.isArray(scenes) || !scenes.length
        || !Array.isArray(structure.character_rigs) || !structure.character_rigs.length) return false
    const parts = structure.character_rigs.flatMap((r: any) => Array.isArray(r?.parts) ? r.parts : [])
    if (!parts.length || parts.length > 32 || new Set(parts.map((p: any) => p?.id)).size !== parts.length) return false
    const ids = new Set(parts.map((p: any) => p?.id))
    const byId = new Map<string, any>(parts.map((p: any) => [p.id, p]))
    for (const part of parts) {
        const seen = new Set([part.id]); let parent = part.parentId
        while (parent) {
            if (!ids.has(parent) || seen.has(parent)) return false
            seen.add(parent); parent = byId.get(parent)?.parentId
        }
    }
    const duration = scenes.reduce((sum: number, s: any) => sum + Number(s.duration_seconds), 0)
    if (!Number.isInteger(duration) || duration < 60 || duration > 600 || structure.target_duration_seconds !== duration) return false
    return scenes.every((s: any, i: number) => s.scene_number === i + 1
        && Number.isFinite(s.duration_seconds) && s.duration_seconds > 0 && s.duration_seconds <= 300
        && typeof s.action_summary === 'string' && s.action_summary.trim().length >= 20
        && typeof s.image_prompt === 'string' && s.image_prompt.trim().length >= 120
        && typeof s.background_prompt === 'string' && s.background_prompt.trim().length >= 120
        && typeof s.direction_prompt === 'string' && s.direction_prompt.trim().length >= 80
        && !s.narration && !s.scene_text && !s.video_prompt && s.video_prompt_required === false
        && s.joint_motion_plan?.contract === 'ae_joint_rig/v1'
        && Array.isArray(s.joint_motion_plan.regions) && s.joint_motion_plan.regions.length > 0
        && Array.isArray(s.scene_timeline?.cues) && s.scene_timeline.cues.length > 0
        && s.scene_timeline.duration === s.duration_seconds
        && s.scene_timeline.cues.every((c: any) => typeof c.id === 'string' && Number.isFinite(c.start) && Number.isFinite(c.end) && c.start >= 0 && c.start < c.end && c.end <= s.duration_seconds)
        && s.joint_motion_plan.regions.every((r: any) => ids.has(r.id) && ['hold','horizontal','vertical','rotate','scale','bend','walk'].includes(r.action)
            && (!r.parentId || s.joint_motion_plan.regions.some((p: any) => p.id === r.parentId))
            && s.scene_timeline.cues.some((c: any) => c.id === r.subtitleId))
        && Array.isArray(s.timed_beats) && s.timed_beats.length > 0)
}
