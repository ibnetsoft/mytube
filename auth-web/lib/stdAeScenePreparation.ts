import { createHash } from 'crypto'
import { aeSceneEffectSelection, aeSceneEffectsMatch } from './stdAeSceneEffects'
import { motionForProject } from './stdMotionStudio'

const active = (asset: any) => ['uploaded', 'assigned'].includes(asset?.status)
const numberOf = (scene: any) => Number(scene?.scene_number ?? scene?.scene_order ?? scene?.number)
const latest = (assets: any[]) => [...assets].sort((a, b) => String(b.created_at || '').localeCompare(String(a.created_at || '')) || String(b.id).localeCompare(String(a.id)))
const sha = (value: unknown) => /^[a-f0-9]{64}$/.test(String(value || ''))

export function canonicalAeScene(value: any): any {
    if (Array.isArray(value)) return value.map(canonicalAeScene)
    if (value && typeof value === 'object') return Object.fromEntries(Object.keys(value).sort().filter(k => value[k] !== undefined).map(k => [k, canonicalAeScene(value[k])]))
    return value
}
export function aeSceneHash(value: any): string {
    return createHash('sha256').update(JSON.stringify(canonicalAeScene(value))).digest('hex')
}
export function aeSceneSources(assets: any[]): Map<number, any> {
    const result = new Map<number, any>()
    for (const asset of latest(assets)) {
        const n = Number(asset.scene_number)
        if (active(asset) && asset.asset_type === 'original' && Number.isInteger(n) && n > 0
            && /\.(psd|psb)$/i.test(String(asset.file_name || ''))
            && (asset.metadata?.gcs_path || asset.metadata?.storage_path) && !result.has(n)) result.set(n, asset)
    }
    return result
}
export function aeSceneSelections(assets: any[]): Map<number, any> {
    const result = new Map<number, any>()
    for (const asset of latest(assets)) {
        const n = Number(asset.scene_number)
        if (active(asset) && asset.metadata?.kind === 'ae_scene_preparation' && !result.has(n)) result.set(n, asset)
    }
    return result
}
export function aeSceneContexts(project: any, scenes: any[]) {
    const saved = project.project_payload?.structure?.scenes || project.project_payload?.scenes || []
    return scenes.map(scene => {
        const number = numberOf(scene)
        const authored = saved.find((s: any) => numberOf(s) === number) || {}
        return {
            scene_number: number,
            scene_title: String(scene.scene_title || authored.scene_title || authored.title || ''),
            scene_text: String(scene.scene_text || authored.scene_text || authored.narration || authored.text || ''),
            image_prompt: String(scene.image_prompt || authored.image_prompt || ''),
            video_prompt: String(scene.video_prompt || authored.video_prompt || ''),
        }
    }).sort((a, b) => a.scene_number - b.scene_number)
}
function reference(asset: any) {
    if (!asset) return undefined
    const m = asset.metadata || {}
    const metadata = Object.fromEntries(['storage_provider', 'gcs_bucket', 'gcs_path', 'storage_bucket', 'storage_path', 'sha256', 'content_identity']
        .filter(key => m[key] !== undefined).map(key => [key, m[key]]))
    return { id: asset.id, asset_type: asset.asset_type, file_name: asset.file_name, mime_type: asset.mime_type, metadata }
}
export function aeScenePreparationInput(project: any, scenes: any[], assets: any[], number: number, direction: string, effects?: unknown) {
    const source = aeSceneSources(assets).get(number)
    if (!source) throw new Error(`${number}번 씬의 원본 PSD를 올려 주세요.`)
    const contexts = aeSceneContexts(project, scenes), index = contexts.findIndex(s => s.scene_number === number)
    if (index < 0) throw new Error('프로젝트에 없는 씬입니다.')
    const visuals = latest(assets).filter(a => active(a) && Number(a.scene_number) === number
        && !a.metadata?.ae_mouth_fingerprint && !a.metadata?.lipsync_fingerprint && !a.metadata?.region_motion_plan_id
        && !['after_effects', 'region_motion'].includes(a.metadata?.postprocess_mode))
    const motion = motionForProject(project)
    const motionScene = motion?.enabled ? motion.scenes[String(number)] : null
    const selectedEffects = motionScene?.source==='psd'
        ? [...new Set([...(aeSceneEffectSelection(effects) || []),...motionScene.effects.map(e=>e.type)])].sort()
        : effects
    return {
        number, source_psd: reference(source), direction_text: direction.trim(),
        ...(motion?.enabled ? {motion_output:{width:motion.aspect==='9:16'?1080:1920,height:motion.aspect==='9:16'?1920:1080},motion_scene:motion.scenes[String(number)] || null} : {}),
        ...(selectedEffects === undefined ? {} : { requested_effects: aeSceneEffectSelection(selectedEffects) }),
        scene_context: contexts[index], neighbors: contexts.filter((_, i) => Math.abs(i - index) === 1),
        ...(visuals.find(a => a.asset_type === 'image') ? { reference_image: reference(visuals.find(a => a.asset_type === 'image')) } : {}),
        ...(visuals.find(a => a.asset_type === 'video') ? { reference_video: reference(visuals.find(a => a.asset_type === 'video')) } : {}),
    }
}
export function hasAeSceneIntent(_project: any, scenes: any[], assets: any[]): boolean {
    const numbers = new Set(scenes.map(numberOf))
    return [...aeSceneSelections(assets)].some(([n, a]) => numbers.has(n) && a.metadata.enabled !== false)
}

/** Never silently fall back to a flattened clip when an AE scene was requested. */
export function preparedAeScenes(project: any, scenes: any[], assets: any[]): Map<number, any> {
    const result = new Map<number, any>()
    const numbers = new Set(scenes.map(numberOf))
    for (const [number, asset] of aeSceneSelections(assets)) {
        const meta = asset.metadata
        if (!numbers.has(number) || meta.enabled === false) continue
        const fail = (reason: string): never => { throw new Error(`${number}번 씬 AE 연출: ${reason}`) }
        if (meta.state !== 'prepared') fail(meta.state === 'failed' ? '준비 작업을 수정한 뒤 다시 요청해 주세요.' : 'PSD와 연출 준비가 끝난 뒤 제출해 주세요.')
        const expected = aeScenePreparationInput(project, scenes, assets, number, String(meta.input?.direction_text || ''), meta.input?.requested_effects)
        // A newly uploaded video can be a planned reference replacement. It must be reviewed again.
        if (meta.fingerprint !== aeSceneHash(expected) || aeSceneHash(meta.input) !== meta.fingerprint) fail('원본·대본·참고 영상이 바뀌었습니다. 연출을 다시 준비해 주세요.')
        const r = meta.result
        if (!aeSceneEffectsMatch(meta.input?.requested_effects, r?.plan)) fail('선택한 효과가 연출 계획과 다릅니다. 다시 준비해 주세요.')
        if (!r || r.plan?.contract !== 'ae_scene/v1' || r.source_asset_id !== expected.source_psd?.id
            || !sha(r.source_sha256) || !sha(r.plan_sha256) || r.plan_sha256 !== aeSceneHash(r.plan)
            || r.review?.passed !== true || !Array.isArray(r.review.critical_issues) || r.review.critical_issues.length
            || r.review.input_fingerprint !== meta.fingerprint || r.review.source_sha256 !== r.source_sha256
            || r.review.plan_sha256 !== r.plan_sha256 || r.review.reviewer !== 'local_codex_cli'
            || !Array.isArray(r.review.evidence) || !r.review.evidence.length
            || !r.review.evidence.every((e: unknown) => typeof e === 'string' && e.trim())
            || !['source_identity_preserved', 'background_complete', 'motion_supported', 'continuity_checked'].every(key => r.review[key] === true)
            || !Array.isArray(r.files) || !r.files.length
            || !r.files.every((f: any) => f.gcs_bucket && f.gcs_path && sha(f.sha256))) fail('검수한 레이어와 연출 기록이 필요합니다.')
        if (!r.files.some((f: any) => f.role === 'source_psd' && f.sha256 === r.source_sha256)
            || !r.files.some((f: any) => f.role === 'source_preview')
            || !r.files.some((f: any) => f.role === 'plan') || !r.files.some((f: any) => f.role === 'review')
            || !r.files.some((f: any) => f.role === 'layer')) fail('원본 PSD·기준 이미지·레이어 파일을 확인해 주세요.')
        result.set(number, asset)
    }
    return result
}
