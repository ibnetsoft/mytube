import { selectNarrationAsset } from './stdContentIdentity'
import { isNonverbalProject } from './stdNonverbal'
import { savedSpeakerGeometry, coordinateCast, coordinateImage, coordinateVideo } from './stdSpeakerGeometry'
import { dialogueSceneIndex, subtitleDialogueSpeakerName } from './stdDialogueSceneIndex'
import { createHash } from 'crypto'
import { isComicProject } from './stdComic'
import { mouthWorkScenes } from './stdMouthWorkPolicy'
import { lipSyncPlan, lipSyncSceneStarts } from './stdLipSync'
import { hasAeSceneIntent, preparedAeScenes } from './stdAeScenePreparation'
import { resolveSceneMedia } from './stdSceneMedia'
import { sceneMotion, sceneMotionSpeed } from './stdSceneMotion'
import { comicSettingsForProject } from './stdComic'
import { aeSceneArtifactReviewMatches, aeSceneRenderReviewMatches, aeSceneSequenceReviewMatches } from './stdAeSceneReview'

const active = (a: any) => ['uploaded', 'assigned'].includes(a.status)
const canonical = (v: any): any => Array.isArray(v) ? v.map(canonical) : v && typeof v === 'object'
    ? Object.fromEntries(Object.keys(v).sort().filter(k => v[k] !== undefined).map(k => [k, canonical(v[k])])) : v

function eyeBlinkPlan(assets: any[], number: number, image: any) {
    if (!image) return null
    const candidates = assets.filter(a => active(a) && a.metadata?.kind === 'eye_blink_confirmation'
        && Number(a.scene_number) === number && a.metadata?.state === 'confirmed'
        && a.metadata?.image_id === image.id)
    // A user's explicit confirmation always wins over generation-time direction,
    // even if the topic receipt was republished later.
    const asset = candidates.find(a => !String(a.id || '').startsWith('generated-eye-blink:')) || candidates[0]
    if (!asset) return null
    const metadata = asset.metadata || {}
    return {
        id: asset.id, version: metadata.version, character: metadata.character,
        image_id: metadata.image_id, source_bucket: metadata.source_bucket,
        source_path: metadata.source_path, source_sha256: metadata.source_sha256,
        left_eye_box: metadata.left_eye_box, right_eye_box: metadata.right_eye_box,
        interval_seconds: metadata.interval_seconds, cues: metadata.cues, reason: metadata.reason,
        confirmed_by: metadata.confirmed_by,
        confirmed_at: metadata.confirmed_at,
    }
}

function approvedLayeredSource(source: any) {
    const asset = source?.metadata?.psd_layer_asset
    if (!asset || typeof asset !== 'object' || asset.qa_status !== 'approved') return null
    const path = String(asset.gcs_path || asset.storage_path || asset.object_path || '')
    if (!path.toLowerCase().endsWith('.psd') || !/^[0-9a-f]{64}$/i.test(String(asset.sha256 || ''))) return null
    return { metadata: {
        ...asset, gcs_path: path,
        gcs_bucket: asset.gcs_bucket || asset.storage_bucket || 'air-studio-prod',
    } }
}

export function aeMouthApplicable(project: any, scenes: any[], assets: any[] = []) {
    return hasAeSceneIntent(project, scenes, assets) ||
        (!isNonverbalProject(project) && !isComicProject(project) && mouthWorkScenes(project, scenes, assets).size > 0)
}

export function aeMouthInput(project: any, scenes: any[], assets: any[]) {
    scenes = [...scenes].sort((a, b) => Number(a.scene_number) - Number(b.scene_number))
    const selected = project.project_payload?.ae_mouth?.enabled === false ? new Set<number>() : mouthWorkScenes(project, scenes, assets)
    const mouthSelected = new Set(selected)
    const savedStructure = project.project_payload?.structure || project.generated_structure || {}
    const explicitMouthSelection = assets.some(a => active(a) && a.metadata?.kind === 'mouth_work_selection') ||
        (savedStructure.scenes || []).some((s: any) => s.metadata?.cowork_image_asset?.speaker_geometry?.mouth_work_selection) ||
        project.project_payload?.mouth_work_policy?.enabled === true || savedStructure.mouth_work_policy?.enabled === true
    const prepared = preparedAeScenes(project, scenes, assets)
    for (const number of prepared.keys()) selected.add(number)
    assets = [...assets].sort((a, b) => String(b.created_at || '').localeCompare(String(a.created_at || '')))
    // Validate the finalized recording, including saved text, voice, direction and timing.
    lipSyncPlan(project, scenes, assets.filter(a => a.asset_type !== 'audio' || a.metadata?.subtitle_timeline?.length))
    const audio = selectNarrationAsset(project, assets)
    const starts = lipSyncSceneStarts(project, scenes, audio)
    const payload = project.project_payload || {}, structure = payload.structure || {}
    const subtitles = (payload.subtitles || []).map((s: any, index: number) => ({
        index, text: String(s.text || ''), scene_number: Number(s.scene_number ?? s.scene ?? s.sceneNumber),
        start: audio.metadata.subtitle_timeline[index].start, end: audio.metadata.subtitle_timeline[index].end,
        voice_id: audio.metadata.subtitle_timeline[index].voice_id || '',
        kind: s.dialogue_kind || '', speaker: subtitleDialogueSpeakerName(s),
        direction: String(s.direction || ''),
    }))
    const input = { version: prepared.size || subtitles.some((r: any) => r.scene_number < 19 && r.kind === 'dialogue') ? 2 : 1, project_id: project.id, tts_speed: payload.tts_speed ?? project.progress_payload?.tts_speed ?? null,
        audio: { id: audio.id, metadata: audio.metadata }, subtitles,
        mouth_work_scene_numbers: scenes.map(s => Number(s.scene_number)).filter(n => selected.has(n)),
        dialogue_scene_index: dialogueSceneIndex(payload.subtitles || []),
        cast: { main: structure.main_character || payload.main_character || {}, supporting: structure.supporting_characters || payload.supporting_characters || [], scene_cast: structure.scene_cast || [] },
        annotations: structure.dialogue_annotations || {},
        ...(prepared.size ? { sequence_scenes: scenes.map((s, index) => {
            const number = Number(s.scene_number), image = coordinateImage(assets, number), video = coordinateVideo(assets, number)
            const aeScene = prepared.get(number)
            const selectedMedia = aeScene ? null : resolveSceneMedia(project, s, assets)
            const requestedTransition = String(s.metadata?.transition_effect || s.transition_effect || '')
            const cutTouchesAe = Boolean(aeScene || (index > 0 && prepared.has(Number(scenes[index - 1].scene_number))))
            return { number, start: starts[index], end: starts[index + 1] ?? subtitles[subtitles.length - 1]?.end,
                text: String(s.scene_text || structure.scenes?.find((r: any) => Number(r.scene_number ?? r.scene_order) === number)?.narration || ''),
                image: image ? { id: image.id, metadata: image.metadata } : null,
                original_video: video ? { id: video.id, metadata: video.metadata } : null,
                selected_media: selectedMedia,
                composition: { image_effect: selectedMedia?.asset_type === 'image' ? sceneMotion(s) : 'none', motion_speed: sceneMotionSpeed(s),
                    comic_panel: comicSettingsForProject(project).panels[String(number)] || null,
                    transition: cutTouchesAe ? 'none' : requestedTransition, requested_transition: requestedTransition,
                    final_layout_pending: true, video_timing: 'final_compositor_pending' },
                ae_scene: aeScene || null }
        }) } : {}),
        scenes: scenes.flatMap((s, index) => {
            const number = Number(s.scene_number)
            if (!selected.has(number)) return []
            const aeScene = prepared.get(number)
            if (aeScene && project.project_payload?.ae_mouth?.enabled !== false && explicitMouthSelection && mouthSelected.has(number) &&
                subtitles.some((row: any) => row.scene_number === number && row.kind === 'dialogue'))
                throw new Error(`${number}번 씬은 AE 장면과 입모양 후작업이 함께 선택돼 있습니다. 입모양 선택을 해제하거나 AE 장면 사용을 끄고 기존 영상의 입모양 후작업을 이용해 주세요.`)
            if (!aeScene && number < 19 && !subtitles.some((r: any) => r.scene_number === number && r.kind === 'dialogue')) return []
            const source = structure.scenes?.find((r: any) => Number(r.scene_number ?? r.scene_order) === number) || s
            const image = coordinateImage(assets, number)
            const originalVideo = coordinateVideo(assets, number)
            const blink = eyeBlinkPlan(assets, number, image)
            if (aeScene && blink && !String(blink.id).startsWith('generated-eye-blink:'))
                throw new Error(`${number}번 씬의 수동 눈깜빡임은 AE 장면과 동시 적용할 수 없습니다. 눈깜빡임 선택을 해제하거나 AE 장면 사용을 꺼 주세요.`)
            if (!aeScene && number < 19 && !originalVideo) throw new Error(`${number}번 대사 씬의 원본 영상이 필요합니다.`)
            if (!aeScene && !image && !originalVideo) throw new Error(`${number}번 씬의 원본 이미지가 필요합니다.`)
            const start = starts[index], end = starts[index + 1] ?? subtitles[subtitles.length - 1]?.end
            if (!Number.isFinite(start) || !Number.isFinite(end) || end < start || (end === start && (aeScene || subtitles.some((t: any) => t.scene_number === number)))) throw new Error(`${number}번 씬의 음성 시간을 확인해 주세요.`)
            const regions = savedSpeakerGeometry(assets, coordinateCast(project), {number,image,
                rows:subtitles.filter((t:any)=>t.scene_number===number && t.kind==='dialogue').map((t:any)=>({speaker:t.speaker}))})
            return [{ number, start, end, speaker_regions: regions || null, text: String(s.scene_text || source.scene_text || source.narration || ''),
                ...(aeScene ? { ae_scene: aeScene } : {}),
                eye_blink: blink,
                layered_source: approvedLayeredSource(source),
                image: image ? { id: image.id, metadata: image.metadata } : null,
                original_video: originalVideo ? { id: originalVideo.id, metadata: originalVideo.metadata } : null,
                direction: { ae_motion_plan: source.ae_motion_plan || null, ae_effect_plan: source.ae_effect_plan || null,
                    image_prompt: source.image_prompt || s.image_prompt || '', ae_directorial_plan: source.ae_directorial_plan || null,
                    scene_direction_plan: source.scene_direction_plan || source.ae_directorial_plan || null },
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
    const runId = (project.submitted_at || project.project_payload?.submission_pipeline_version === 2) && project.progress_payload?.pipeline_run_id
    if (runId) {
        const frozen = assets.find(a => active(a) && a.metadata?.kind === 'ae_mouth_job' && a.metadata?.pipeline_run_id === runId)
        if (frozen) return frozen
    }
    if (!aeMouthApplicable(project, scenes, assets)) return null
    const { input, fingerprint } = aeMouthInput(project, scenes, assets)
    return [...assets].sort((a, b) => String(b.created_at || '').localeCompare(String(a.created_at || ''))).find(a => active(a) && a.metadata?.kind === 'ae_mouth_job' && (a.metadata.fingerprint === fingerprint || compatibleMouthInput(a.metadata.input, input))) || null
}

export function reviewedAeMouthAssets(project: any, scenes: any[], assets: any[]) {
    const result = new Map<number, any>()
    const runId = project.progress_payload?.pipeline_run_id
    const requiredFrozen = runId && assets.some(a => active(a) && a.metadata?.kind === 'ae_mouth_job' &&
        a.metadata.pipeline_run_id === runId && a.metadata.input?.scenes?.some((scene: any) => scene.ae_scene))
    const requiredActive = hasAeSceneIntent(project, scenes, assets)
    if (!project.project_payload?.ae_mouth?.enabled && !requiredFrozen && !requiredActive) return result
    const job = currentAeMouthJob(project, scenes, assets)
    if (job?.metadata?.pipeline_version === 2) return readyPipelineMouthAssets(job, assets)
    if (requiredActive || requiredFrozen || job?.metadata?.input?.scenes?.some((scene: any) => scene.ae_scene))
        throw new Error('AE 장면은 제출 단계에서 원본·음성·연출을 확정한 뒤 제작과 검수를 완료해 주세요.')
    if (job?.metadata?.state !== 'reviewed' && !(job?.metadata?.automatic === true && job.metadata.state === 'processing' && job.metadata.phase === 'auto_enqueue')) throw new Error('대사 영상과 정지 씬의 AE 입모양 후작업·검수를 완료해 주세요.')
    const numbers = (job.metadata.input?.scenes || aeMouthInput(project, scenes, assets).input.scenes).map((s: any) => Number(s.number))
    const checked = job.metadata.results || []
    if (checked.length !== numbers.length || numbers.some((n: number) => checked.filter((r: any) => r.number === n).length !== 1)) {
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

/** Technical contracts are distinct from historical model approval. */
export function readyPipelineMouthAssets(job: any, assets: any[]) {
    if (!['artifact_ready', 'processing'].includes(job.metadata.state) ||
        (job.metadata.state === 'processing' && job.metadata.phase !== 'auto_enqueue'))
        throw new Error('입모양 영상 합성이 진행 중입니다.')
    const result = new Map<number, any>()
    for (const scene of job.metadata.input.scenes) {
        const rows = job.metadata.results.filter((r: any) => r.number === scene.number)
        if (rows.length !== 1) throw new Error(`${scene.number}번 씬의 처리 결과가 없습니다.`)
        const row = rows[0]
        if (!scene.ae_scene && row.status === 'skipped' && (!row.skip_reason || row.fallback === 'original')) continue
        if (row.status !== 'artifact_ready') throw new Error(`${scene.number}번 영상 합성이 완료되지 않았습니다.`)
        const asset = assets.find(a => active(a) && a.id === row.asset_id && a.asset_type === 'video')
        if (!asset || asset.metadata?.kind === 'mouth_preview' || asset.metadata?.timing_mode === 'preview_cycle' ||
            asset.metadata?.voice_synced === false || asset.metadata?.artifact_ready !== true || asset.metadata.source_audio_id !== job.metadata.input.audio.id ||
            asset.metadata.render_sha256 !== row.render_sha256 || asset.metadata.ae_mouth_fingerprint !== job.metadata.fingerprint ||
            !asset.metadata.timing_locked || Number(asset.scene_number) !== scene.number ||
            Math.abs(Number(asset.metadata.duration_seconds) - (scene.end - scene.start)) > .12)
            throw new Error(`${scene.number}번 영상 파일·음성·시간 연결이 일치하지 않습니다.`)
        if (scene.ae_scene) {
            if (!aeSceneArtifactReviewMatches(scene, job.metadata.input.audio, asset.metadata) ||
                !aeSceneRenderReviewMatches(scene, job.metadata.input.audio, row.output_review, row.render_sha256))
                throw new Error(`${scene.number}번 AE 장면의 원본·연출·출력 검수가 일치하지 않습니다.`)
        }
        result.set(scene.number, asset)
    }
    if (job.metadata.input.scenes.some((scene: any) => scene.ae_scene)) {
        const review = job.metadata.sequence_review
        if (review?.fingerprint !== aeSceneSequenceFingerprint(job) ||
            !aeSceneSequenceReviewMatches(job.metadata.input.sequence_scenes, job.metadata.results, review))
            throw new Error('AE 장면 사이 연결 검수가 완료되지 않았습니다.')
    }
    return result
}

/** Bind the sequence receipt to the frozen input and exact selected output files. */
export function aeSceneSequenceFingerprint(job: any) {
    const rows = job.metadata.input.scenes.map((scene: any) => {
        const row = job.metadata.results.find((r: any) => r.number === scene.number) || {}
        return [scene.number, row.status || null, row.asset_id || null, row.render_sha256 || null]
    })
    return createHash('sha256').update(JSON.stringify([job.metadata.fingerprint, rows])).digest('hex')
}
