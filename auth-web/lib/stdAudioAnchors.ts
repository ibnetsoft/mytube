import { sceneAudioAnchor } from './stdSceneAudioAnchor'
import { resolveSfxCues } from './stdSfxCues'

// Capture legacy selections BEFORE replacing the subtitle array. Existing anchors
// remain immutable until the user explicitly chooses a different position.
export function preserveAudioAnchors(previous: any, next: any) {
    const old = previous?.render_settings || {}
    const settings = { ...old, ...(next?.render_settings || {}) }
    const before = previous?.subtitles || []
    const after = next?.subtitles || before
    const changed = ['bgm_start_scene', 'bgm_start_subtitle'].some(key => Number(settings[key] ?? 1) !== Number(old[key] ?? 1))
    if (!changed && old.bgm_start_anchor) settings.bgm_start_anchor = old.bgm_start_anchor
    if (changed || !settings.bgm_start_anchor) {
        const rows = changed || !before.length ? after : before
        const candidates = rows.flatMap((row: any, index: number) => Number(row.scene_number) === Number(settings.bgm_start_scene) ? [index] : [])
        settings.bgm_start_anchor = sceneAudioAnchor(rows, candidates[Number(settings.bgm_start_subtitle ?? 1) - 1])
    }
    if (!Array.isArray(settings.sfx_cues) && Array.isArray(next?.sfx_cues || previous?.sfx_cues)) settings.sfx_cues = next?.sfx_cues || previous.sfx_cues
    if (Array.isArray(settings.sfx_cues)) settings.sfx_cues = settings.sfx_cues.map((cue: any) => {
        const prior = (old.sfx_cues || previous?.sfx_cues || []).find((c: any) => c.id === cue.id)
        const moved = !prior || prior.subtitle_id !== cue.subtitle_id || prior.scene_number !== cue.scene_number || prior.word_boundary !== cue.word_boundary
        const source = moved ? { ...cue, scene_anchor: undefined } : { ...cue, scene_anchor: prior.scene_anchor || cue.scene_anchor }
        const resolved = resolveSfxCues([{ ...source, enabled: true }], moved || !before.length ? after : before)[0]
        // Preserve unresolved/disabled cues for explicit review, never reattach by index.
        return { ...cue, ...(resolved?.scene_anchor ? { scene_anchor: resolved.scene_anchor } : {}) }
    })
    return { ...next, render_settings: settings }
}
