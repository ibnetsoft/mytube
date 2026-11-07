import { ambientFrameIndex, ambientLoopsForState } from './stdAmbientLoop'
import { mouthMatchesRecording, wuxiaMouthFrame, stateMouths } from './stdWuxiaMouth'
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
// Correct the original first-scene layout only while that exact image and
// original placement remain in use. Artist-edited layouts remain authoritative.
export function correctedWuxiaPackage(pkg: any) {
    if (!Array.isArray(pkg?.scenes)) return pkg
    return { ...pkg, scenes: pkg.scenes.map((scene: any) => {
        const state = scene.states?.find((item: any) => item.sha256 === '18feb83a4b3cd8873870adc0e13baffc75f3693afeeb568951074593915977dc')
        if (!state || !Array.isArray(scene.graphics)) return scene
        return { ...scene, graphics: scene.graphics.map((g: any) => {
            if (g.state_asset_id !== state.asset_id || g.kind !== 'speech_bubble' || g.text !== '짐꾼. 거기 서 있지 말고 내려놔.' || g.layout?.center?.[0] !== 0.29 || g.layout?.center?.[1] !== 0.19) return g
            return { ...g, layout: { ...g.layout, center: [0.49, 0.14], size: [0.30, 0.20], tail: [0.22, 0.30] } }
        }) }
    }) }
}
export function wuxiaSceneFrame(project: any, number: number, rows: any[], seconds: number) {
    const p = project?.project_payload || project || {}
    if (!isWuxiaMovingtoon(project)) return null
    const pkg = correctedWuxiaPackage(p.structure?.wuxia_ae_package || p.wuxia_ae_package)
    const scene = pkg?.scenes?.find((s: any) => Number(String(s.scene_id).match(/S(\d+)$/)?.[1]) === number)
    if (!scene) return null
    const timing = rows.filter(r => Number(r.scene_number) === number)
    const start = Math.min(...timing.map(r => Number(r.start_num ?? r.start_time)))
    const end = Math.max(...timing.map(r => Number(r.end_num ?? r.end_time)))
    const fraction = Number.isFinite(start) && end > start ? Math.max(0, Math.min(.999999, (seconds - start) / (end - start))) : 0
    const normalize = (value: any) => String(value || '').replace(/[\s\p{P}\p{S}]/gu, '')
    // Match a frozen sentence across any number of split voice rows.
    // Punctuation-only rows contribute no text and never reset the speaker.
    const rowRange = (g: any) => {
        const target = normalize(g.voice_binding?.exact_anchor || g.text)
        if (!target) return null
        let joined = '', parts: any[] = []
        for (const r of timing) {
            const text = normalize(r.text), from = joined.length
            const start = Number(r.start_num ?? r.start_time), end = Number(r.end_num ?? r.end_time)
            if (!text || !Number.isFinite(start) || !Number.isFinite(end) || end <= start) continue
            joined += text; parts.push({ from, to: joined.length, start, end })
        }
        const at = joined.indexOf(target)
        if (at < 0 || joined.indexOf(target, at + 1) >= 0) return null
        const first = parts.find(r => r.from <= at && at < r.to)
        const last = parts.find(r => r.from < at + target.length && at + target.length <= r.to)
        if (!first || !last) return null
        return {
            start: first.start + (first.end - first.start) * (at - first.from) / (first.to - first.from),
            end: last.start + (last.end - last.start) * (at + target.length - last.from) / (last.to - last.from),
        }
    }
    const dialogue = (scene.graphics || []).find((g: any) => {
        const range = rowRange(g)
        return range && seconds >= range.start && seconds < range.end
    })
    const scheduled = scene.states?.find((s: any) => fraction >= s.start && fraction < s.end) || scene.states?.[0]
    // A derived acting state inherits the graphics of its source image.
    const scheduledSource = scheduled?.parent_asset_id || scheduled?.asset_id
    const state = dialogue && scheduledSource !== dialogue.state_asset_id
        ? scene.states?.find((s: any) => s.asset_id === dialogue.state_asset_id) || scheduled
        : scheduled
    const graphics = (scene.graphics || []).filter((g: any) => {
        if (g.state_asset_id !== (state?.parent_asset_id || state?.asset_id)) return false
        const range = rowRange(g)
        return range ? seconds >= range.start && seconds < range.end : fraction >= g.preview_start && fraction < g.preview_end
    }).map((g: any) => {
        const range = rowRange(g)
        const progress = range ? (seconds-range.start)/(range.end-range.start) : (fraction-g.preview_start)/(g.preview_end-g.preview_start)
        return { ...g, progress: Math.max(0, Math.min(1, progress)) }
    })
    // Scene-local clock is continuous through a state cut, pause and seek.
    // Explicit start_ms controls restart/phase; wall-clock time is never used.
    const localMs = Number.isFinite(start) ? (seconds-start)*1000 : 0
    const ambient = ambientLoopsForState(state).flatMap(loop => {
        const index = ambientFrameIndex(loop, localMs)
        return index === null ? [] : [{ loop, index, frame: loop.frames[index] }]
    })
    const ambientSources = (scene.states || []).flatMap((item: any) => ambientLoopsForState(item).filter(loop => loop.enabled).flatMap(loop => loop.frames.map(f=>({...f,region:loop.region,width:loop.width,height:loop.height}))))
    const mouths=wuxiaMouthFrame(state,graphics,project,rows,seconds)
    const mouthSources=(scene.states||[]).flatMap((item:any)=>stateMouths(item).filter((m:any)=>m?.enabled&&m.source_sha256===item.sha256&&mouthMatchesRecording(m,project,rows)).flatMap((m:any)=>Object.values(m.poses).map((f:any)=>({...f,region:m.mouth_box,width:m.width,height:m.height}))))
    return { state, graphics, fraction, ambient, ambientSources, mouths, mouthSources, sources: (scene.states || []).map((item: any) => String(item.media_url || item.image_url || '')).filter(Boolean), timingBasis: 'subtitle_row_bound_or_authored_preview' }
}
