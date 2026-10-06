import { savedSpeakerGeometry, coordinateCast } from './stdSpeakerGeometry'
import { dialogueSceneIndex } from './stdDialogueSceneIndex'
import { createHash } from 'crypto'
import { isComicProject } from './stdComic'
import { lipSyncPlan, lipSyncSceneStarts } from './stdLipSync'

const active = (a: any) => ['uploaded', 'assigned'].includes(a.status)
const canonical = (v: any): any => Array.isArray(v) ? v.map(canonical) : v && typeof v === 'object'
    ? Object.fromEntries(Object.keys(v).sort().filter(k => v[k] !== undefined).map(k => [k, canonical(v[k])])) : v

export function aeMouthApplicable(project: any, scenes: any[]) {
    return !isComicProject(project) && scenes.some(s => Number(s.scene_number) >= 19)
}

export function aeMouthInput(project: any, scenes: any[], assets: any[]) {
    assets = [...assets].sort((a, b) => String(b.created_at || '').localeCompare(String(a.created_at || '')))
    // Validate the finalized recording, including saved text, voice, direction and timing.
    lipSyncPlan(project, scenes, assets)
    const audio = assets.find(a => active(a) && a.asset_type === 'audio')
    const starts = lipSyncSceneStarts(project, scenes, audio)
    const payload = project.project_payload || {}, structure = payload.structure || {}
    const subtitles = (payload.subtitles || []).map((s: any, index: number) => ({
        index, text: String(s.text || ''), scene_number: Number(s.scene_number ?? s.scene ?? s.sceneNumber),
        start: audio.metadata.subtitle_timeline[index].start, end: audio.metadata.subtitle_timeline[index].end,
        voice_id: audio.metadata.subtitle_timeline[index].voice_id || '',
        kind: s.dialogue_kind || '', speaker: s.dialogue_speaker || '',
        direction: String(s.direction || ''),
    }))
    const input = { version: 1, project_id: project.id, tts_speed: payload.tts_speed ?? project.progress_payload?.tts_speed ?? null,
        audio: { id: audio.id, metadata: audio.metadata }, subtitles,
        dialogue_scene_index: dialogueSceneIndex(payload.subtitles || []),
        cast: { main: structure.main_character || payload.main_character || {}, supporting: structure.supporting_characters || payload.supporting_characters || [], scene_cast: structure.scene_cast || [] },
        annotations: structure.dialogue_annotations || {},
        scenes: scenes.flatMap((s, index) => {
            const number = Number(s.scene_number)
            if (number < 19) return []
            const source = structure.scenes?.find((r: any) => Number(r.scene_number ?? r.scene_order) === number) || s
            const image = assets.find(a => active(a) && a.asset_type === 'image' && Number(a.scene_number) === number)
            const originalVideo = assets.find(a => active(a) && a.asset_type === 'video' && Number(a.scene_number) === number
                && !a.metadata?.ae_mouth_fingerprint && !a.metadata?.lipsync_fingerprint && a.metadata?.postprocess_mode !== 'after_effects')
            if (!image && !originalVideo) throw new Error(`${number}번 씬의 원본 이미지가 필요합니다.`)
            const start = starts[index], end = starts[index + 1] ?? subtitles[subtitles.length - 1]?.end
            if (!Number.isFinite(start) || !Number.isFinite(end) || end < start || (end === start && subtitles.some((t: any) => t.scene_number === number))) throw new Error(`${number}번 씬의 음성 시간을 확인해 주세요.`)
            const regions = savedSpeakerGeometry(assets, coordinateCast(project), {number,image,
                rows:subtitles.filter((t:any)=>t.scene_number===number && t.kind==='dialogue').map((t:any)=>({speaker:t.speaker}))})
            return [{ number, start, end, speaker_regions: regions || null, text: String(s.scene_text || source.scene_text || source.narration || ''),
                image: image ? { id: image.id, metadata: image.metadata } : null,
                original_video: originalVideo ? { id: originalVideo.id, metadata: originalVideo.metadata } : null,
                direction: { ae_motion_plan: source.ae_motion_plan || null, ae_effect_plan: source.ae_effect_plan || null,
                    image_prompt: source.image_prompt || s.image_prompt || '', ae_directorial_plan: source.ae_directorial_plan || null },
            }]
        }),
    }
    const fingerprint = createHash('sha256').update(JSON.stringify(canonical(input))).digest('hex')
    return { input, fingerprint }
}

export function currentAeMouthJob(project: any, scenes: any[], assets: any[]) {
    if (!aeMouthApplicable(project, scenes)) return null
    const { fingerprint } = aeMouthInput(project, scenes, assets)
    return [...assets].sort((a, b) => String(b.created_at || '').localeCompare(String(a.created_at || ''))).find(a => active(a) && a.metadata?.kind === 'ae_mouth_job' && a.metadata.fingerprint === fingerprint) || null
}

export function reviewedAeMouthAssets(project: any, scenes: any[], assets: any[]) {
    const result = new Map<number, any>()
    if (!project.project_payload?.ae_mouth?.enabled) return result
    const job = currentAeMouthJob(project, scenes, assets)
    if (job?.metadata?.state !== 'reviewed') throw new Error('19씬 이후 대사 장면의 AE 입모양 후작업·검수를 완료해 주세요.')
    const numbers = scenes.filter(s => Number(s.scene_number) >= 19).map(s => Number(s.scene_number))
    const checked = job.metadata.results || []
    if (checked.length !== numbers.length || numbers.some(n => checked.filter((r: any) => r.number === n).length !== 1)) {
        throw new Error('19씬 이후 모든 씬의 대사 판별 결과가 필요합니다.')
    }
    for (const row of job.metadata.results || []) {
        if (row.status === 'skipped') continue
        if (row.status !== 'approved') throw new Error(`${row.number}번 씬의 AE 입모양 검수가 필요합니다.`)
        const asset = assets.find(a => active(a) && a.asset_type === 'video' && a.id === row.asset_id
            && a.metadata?.ae_mouth_fingerprint === job.metadata.fingerprint && a.metadata.ae_reviewed === true
            && a.metadata.render_sha256 === row.render_sha256
            && a.metadata.timing_locked === true && Number(a.scene_number) === row.number
            && Math.abs(Number(a.metadata.duration_seconds) - Number(row.duration)) <= .12)
        if (!asset) throw new Error(`${row.number}번 씬의 검수된 AE 영상이 현재 음성과 일치하지 않습니다.`)
        result.set(row.number, asset)
    }
    return result
}
