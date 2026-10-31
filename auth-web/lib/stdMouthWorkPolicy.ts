/** The source worker freezes its scope; speech edits never expand it. */
function preparedStillMouthScenes(project: any, scenes: any[], assets: any[] = []): Set<number> {
    const payload = project.project_payload || {}
    const structure = payload.structure || project.generated_structure || {}
    const scope = structure.effect_scene_range
    const inScope = (n: number) => !scope || (Number.isInteger(scope.start) && Number.isInteger(scope.end) && n >= scope.start && n <= scope.end)
    const receipt = assets.find(a => a.metadata?.kind === 'mouth_work_selection')?.metadata || (structure.scenes || []).map((s: any) =>
        s.metadata?.cowork_image_asset?.speaker_geometry?.mouth_work_selection).find(Boolean)
    if (receipt && Array.isArray(receipt.scene_numbers)) return new Set<number>(receipt.scene_numbers.map(Number).filter(inScope))
    const policy = payload.mouth_work_policy || structure.mouth_work_policy || {}
    if (policy.enabled === false) return new Set()
    const start = Number.isInteger(policy.start_scene) ? policy.start_scene : 19
    const count = Number.isInteger(policy.max_dialogue_scenes) ? Math.max(0, policy.max_dialogue_scenes) : 10
    const known = new Set(scenes.map((s: any) => Number(s.scene_number)))
    const numbers = (payload.subtitles || []).filter((r: any) => r.dialogue_kind === 'dialogue'
        && String(r.text || '').trim()).map((r: any) => Number(r.scene_number ?? r.scene ?? r.sceneNumber))
    return new Set([...new Set<number>(numbers)].filter(n => n >= start && known.has(n) && inScope(n)).sort((a, b) => a - b).slice(0, count))
}

export function mouthWorkScenes(project:any,scenes:any[],assets:any[]=[]):Set<number> {
    const selected=preparedStillMouthScenes(project,scenes,assets)
    const known=new Set(scenes.map(s=>Number(s.scene_number)))
    const scope=(project.project_payload?.structure || project.generated_structure || {}).effect_scene_range
    const videos=new Set(assets.filter(a=>a.asset_type==='video'&&['uploaded','assigned'].includes(a.status)&&!a.metadata?.ae_mouth_fingerprint&&!a.metadata?.lipsync_fingerprint).map(a=>Number(a.scene_number)))
    for(const row of project.project_payload?.subtitles||[]) {
        const n=Number(row.scene_number??row.scene??row.sceneNumber)
        if(!scope&&n>=1&&n<=18&&known.has(n)&&videos.has(n)&&row.dialogue_kind==='dialogue'&&String(row.text||'').trim())selected.add(n)
    }
    return selected
}
