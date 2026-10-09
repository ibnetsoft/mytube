import { savedSpeakerGeometry, coordinateCast, coordinateImage, coordinateVideo } from './stdSpeakerGeometry'
import { dialogueSceneIndex, subtitleDialogueSpeakerName } from './stdDialogueSceneIndex'
import { createHash } from 'crypto'
import { isComicProject } from './stdComic'
import { lipSyncPlan, lipSyncSceneStarts } from './stdLipSync'

const active = (a: any) => ['uploaded', 'assigned'].includes(a.status)
const canonical = (v: any): any => Array.isArray(v) ? v.map(canonical) : v && typeof v === 'object'
    ? Object.fromEntries(Object.keys(v).sort().filter(k => v[k] !== undefined).map(k => [k, canonical(v[k])])) : v

export function aeMouthApplicable(project: any, scenes: any[]) {
    return !isComicProject(project) && scenes.some(s => Number(s.scene_number) >= 19 || (project.project_payload?.subtitles || []).some((r: any) => Number(r.scene_number) === Number(s.scene_number) && r.dialogue_kind === 'dialogue'))
}

export function aeMouthInput(project: any, scenes: any[], assets: any[]) {
    assets = [...assets].sort((a, b) => String(b.created_at || '').localeCompare(String(a.created_at || '')))
    // Validate the finalized recording, including saved text, voice, direction and timing.
    lipSyncPlan(project, scenes, assets.filter(a => a.asset_type !== 'audio' || a.metadata?.subtitle_timeline?.length))
    const audio = assets.find(a => active(a) && a.asset_type === 'audio' && Array.isArray(a.metadata?.subtitle_timeline) && a.metadata.subtitle_timeline.length)
    const starts = lipSyncSceneStarts(project, scenes, audio)
    const payload = project.project_payload || {}, structure = payload.structure || {}
    const subtitles = (payload.subtitles || []).map((s: any, index: number) => ({
        index, text: String(s.text || ''), scene_number: Number(s.scene_number ?? s.scene ?? s.sceneNumber),
        start: audio.metadata.subtitle_timeline[index].start, end: audio.metadata.subtitle_timeline[index].end,
        voice_id: audio.metadata.subtitle_timeline[index].voice_id || '',
        kind: s.dialogue_kind || '', speaker: subtitleDialogueSpeakerName(s),
        direction: String(s.direction || ''),
    }))
    const input = { version: subtitles.some((r: any) => r.scene_number < 19 && r.kind === 'dialogue') ? 2 : 1, project_id: project.id, tts_speed: payload.tts_speed ?? project.progress_payload?.tts_speed ?? null,
        audio: { id: audio.id, metadata: audio.metadata }, subtitles,
        dialogue_scene_index: dialogueSceneIndex(payload.subtitles || []),
        cast: { main: structure.main_character || payload.main_character || {}, supporting: structure.supporting_characters || payload.supporting_characters || [], scene_cast: structure.scene_cast || [] },
        annotations: structure.dialogue_annotations || {},
        scenes: scenes.flatMap((s, index) => {
            const number = Number(s.scene_number)
            if (number < 19 && !subtitles.some((r: any) => r.scene_number === number && r.kind === 'dialogue')) return []
            const source = structure.scenes?.find((r: any) => Number(r.scene_number ?? r.scene_order) === number) || s
            const image = coordinateImage(assets, number)
            const originalVideo = coordinateVideo(assets, number)
            if (number < 19 && !originalVideo) throw new Error(`${number}번 대사 씬의 원본 영상이 필요합니다.`)
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

function compatibleMouthInput(saved: any, current: any) {
    if (!saved?.scenes || !current?.scenes) return false
    const withoutRegions = (value: any) => ({ ...value, scenes: value.scenes.map(({ speaker_regions, ...scene }: any) => scene) })
    if (JSON.stringify(canonical(withoutRegions(saved))) !== JSON.stringify(canonical(withoutRegions(current)))) return false
    // New results for previously unresolved scenes must not discard already prepared AE work.
    // Corrections to coordinates that this job actually used still invalidate it.
    return saved.scenes.every((scene: any, index: number) => !scene.speaker_regions ||
        JSON.stringify(canonical(scene.speaker_regions)) === JSON.stringify(canonical(current.scenes[index].speaker_regions)))
}

export function currentAeMouthJob(project: any, scenes: any[], assets: any[]) {
    if (!aeMouthApplicable(project, scenes)) return null
    const { input, fingerprint } = aeMouthInput(project, scenes, assets)
    return [...assets].sort((a, b) => String(b.created_at || '').localeCompare(String(a.created_at || ''))).find(a => active(a) && a.metadata?.kind === 'ae_mouth_job' && (a.metadata.fingerprint === fingerprint || compatibleMouthInput(a.metadata.input, input))) || null
}

export function reviewedAeMouthAssets(project: any, scenes: any[], assets: any[]) {
    const result = new Map<number, any>()
    if (!project.project_payload?.ae_mouth?.enabled) return result
    const job = currentAeMouthJob(project, scenes, assets)
    if (job?.metadata?.state !== 'reviewed') throw new Error('대사 영상과 정지 씬의 AE 입모양 후작업·검수를 완료해 주세요.')
    const numbers = (job.metadata.input?.scenes || aeMouthInput(project, scenes, assets).input.scenes).map((s: any) => Number(s.number))
    const checked = job.metadata.results || []
    if (checked.length !== numbers.length || numbers.some(n => checked.filter((r: any) => r.number === n).length !== 1)) {
        throw new Error('작업 대상 씬 모두의 대사 판별 결과가 필요합니다.')
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
