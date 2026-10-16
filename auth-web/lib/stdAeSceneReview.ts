import { aeSceneHash } from './stdAeScenePreparation'

// Keep this receipt contract aligned with worker/ae_scene_review_contract.py.
export const AE_RENDER_CHECKS = ['source_identity', 'layer_seams', 'camera_path', 'deformation',
    'lighting', 'transition', 'visual_quality', 'narration_integrity']
export const AE_BOUNDARY_CHECKS = ['character_identity', 'screen_direction', 'action_continuity',
    'lighting_continuity', 'edit_intent', 'visual_quality']
const number = (value: any) => typeof value === 'number' && Number.isFinite(value)
const hash = (value: any) => typeof value === 'string' && /^[0-9a-f]{64}$/.test(value)
const close = (left: any, right: any, tolerance = 1e-6) => number(left) && number(right) && Math.abs(left - right) <= tolerance
function validReview(review: any, required: string[]) {
    const checks = review?.checks
    return review?.passed === true && Array.isArray(review.critical_issues) && review.critical_issues.length === 0 &&
        Array.isArray(checks) && checks.length === required.length &&
        new Set(checks.map(check => check?.id)).size === required.length &&
        checks.every(check => required.includes(check?.id) && check.passed === true &&
            typeof check.evidence === 'string' && check.evidence.trim().length > 0)
}

export function aeSceneReviewSampleTimes(plan: any, duration: number, fps = 24) {
    const keys = new Set<number>([0, 1, .25, .5, .75])
    const timelines = [plan.camera]
    for (const layer of plan.layers) {
        if (layer.motion) timelines.push(layer.motion)
        if (layer.bend) timelines.push(layer.bend.keys)
    }
    timelines.push(...(plan.lights || []).map((light: any) => light.keys))
    for (const timeline of timelines) {
        for (let i = 0; i < timeline.length; i++) {
            keys.add(timeline[i].t)
            if (i) keys.add((timeline[i - 1].t + timeline[i].t) / 2)
        }
    }
    if (plan.transition.in === 'fade') {
        keys.add(plan.transition.fraction / 2); keys.add(plan.transition.fraction)
    }
    if (plan.transition.out === 'fade') {
        keys.add(1 - plan.transition.fraction); keys.add(1 - plan.transition.fraction / 2)
    }
    const lastFrame = Math.max(0, Math.ceil(duration * fps - 1e-7) - 1)
    return [...new Set([...keys].map(t => Math.min(lastFrame, Math.max(0, Math.floor(t * duration * fps + .5))) / fps))].sort((a, b) => a - b)
}

/** Validate actual sampled pixels and finalized audio, not just a passed flag. */
export function aeSceneRenderReviewMatches(scene: any, audio: any, review: any, renderSha256: any) {
    try {
        const result = scene.ae_scene.metadata.result, plan = result.plan
        const duration = scene.end - scene.start
        if (!number(duration) || duration <= 0 || !hash(renderSha256) || review?.passed !== true || review.version !== 1 ||
            review.method !== 'sampled_actual_frames_and_decoded_final_audio' || review.render_sha256 !== renderSha256 ||
            !hash(result.source_sha256) || review.source_sha256 !== result.source_sha256 ||
            !hash(result.plan_sha256) || review.plan_sha256 !== result.plan_sha256 || aeSceneHash(plan) !== result.plan_sha256) return false
        const previews = result.files.filter((file: any) => file.role === 'source_preview')
        if (previews.length !== 1 || !hash(previews[0].sha256) || review.source_preview_sha256 !== previews[0].sha256) return false
        const voice = review.audio || {}
        if (!audio?.id || voice.source_audio_id !== audio.id || !hash(voice.final_audio_sha256) ||
            voice.method !== 'decoded_pcm_integrity_not_audio_audition' || voice.sample_rate !== 8000 ||
            !close(voice.scene_start_seconds, scene.start) || !close(voice.scene_end_seconds, scene.end) ||
            !number(voice.correlation) || voice.correlation < .9 || voice.correlation > 1.00001 ||
            !number(voice.rms_ratio) || voice.rms_ratio < .8 || voice.rms_ratio > 1.2) return false
        if (audio.metadata?.sha256 && voice.final_audio_sha256 !== audio.metadata.sha256) return false
        for (const key of ['source_samples', 'output_samples']) {
            if (!number(voice[key]) || voice[key] <= 0 || !Number.isInteger(voice[key]) || Math.abs(voice[key] - duration * 8000) > 960) return false
        }
        const video = review.video || {}, output = plan.output || { width: 1920, height: 1080 }
        if (!close(video.fps, 24, .001) || !number(video.frames) || video.frames < 1 || !Number.isInteger(video.frames) ||
            !close(video.duration, video.frames / video.fps) || !close(video.duration, duration, 1 / 24 + .01) ||
            video.width !== output.width || video.height !== output.height) return false
        if (!Array.isArray(review.batches) || !review.batches.length) return false
        const observed: number[] = []
        for (const batch of review.batches) {
            if (!validReview(batch?.review, AE_RENDER_CHECKS) || !Array.isArray(batch.seconds) || !batch.seconds.length ||
                !Array.isArray(batch.frames) || batch.frames.length !== batch.seconds.length) return false
            for (let i = 0; i < batch.seconds.length; i++) {
                const t = batch.seconds[i], frame = batch.frames[i]
                if (!number(t) || t < 0 || t >= duration || !close(frame?.seconds, t) || !hash(frame?.sha256)) return false
            }
            observed.push(...batch.seconds)
        }
        return aeSceneReviewSampleTimes(plan, duration).every(t => observed.some(actual => close(t, actual, 1e-5)))
    } catch { return false }
}

export function aeSceneArtifactReviewMatches(scene: any, audio: any, metadata: any) {
    const prepared = scene.ae_scene, result = prepared?.metadata?.result
    return !!result && metadata?.kind === 'ae_scene_output' && metadata.ae_reviewed === true &&
        metadata.ae_scene_preparation_id === prepared.id &&
        metadata.ae_scene_preparation_fingerprint === prepared.metadata.fingerprint &&
        metadata.plan_sha256 === result.plan_sha256 && metadata.source_psd_id === result.source_asset_id &&
        metadata.source_sha256 === result.source_sha256 &&
        aeSceneRenderReviewMatches(scene, audio, metadata.ae_scene_review, metadata.render_sha256)
}

/** Bind every visible adjacent cut to the exact frozen input or rendered file. */
export function aeSceneSequenceReviewMatches(scenes: any[], outcomes: any[], review: any) {
    try {
        const ordered = [...scenes].sort((a, b) => a.number - b.number)
        if (new Set(ordered.map(s => s.number)).size !== ordered.length) return false
        const visible = ordered.filter(scene => {
            if (!number(scene.start) || !number(scene.end) || scene.start < 0 || scene.end < scene.start ||
                (scene.ae_scene && scene.end - scene.start <= .001)) throw new Error('Invalid frozen scene timing')
            return scene.end - scene.start > .001
        })
        const aeNumbers = visible.filter(s => s.ae_scene).map(s => s.number)
        if (review?.passed !== true || review.version !== 1 || review.method !== 'sampled_actual_adjacent_frames' ||
            JSON.stringify(review.ae_scene_numbers) !== JSON.stringify(aeNumbers)) return false
        const expected = visible.slice(1).flatMap((right, i) => visible[i].ae_scene || right.ae_scene ? [[visible[i], right]] : [])
        if (!Array.isArray(review.checked_boundaries) || review.checked_boundaries.length !== expected.length) return false
        for (let i = 0; i < expected.length; i++) {
            const [left, right] = expected[i], boundary = review.checked_boundaries[i]
            if (boundary?.from !== left.number || boundary.to !== right.number || !validReview(boundary.review, AE_BOUNDARY_CHECKS) ||
                !Array.isArray(boundary.evidence) || boundary.evidence.length !== 2) return false
            for (let j = 0; j < 2; j++) {
                const actual = boundary.evidence[j], scene = [left, right][j]
                if (actual?.number !== scene.number || !hash(actual.media_sha256)) return false
                const rows = outcomes.filter(row => row.number === scene.number)
                if (rows.length > 1) return false
                const row = rows[0]
                if (row && row.status !== 'skipped') {
                    if (!hash(row.render_sha256) || actual.kind !== 'actual_postprocessed_output' || actual.media_sha256 !== row.render_sha256) return false
                } else {
                    if (scene.ae_scene) return false
                    const hasSelection = Object.prototype.hasOwnProperty.call(scene, 'selected_media')
                    const selected = hasSelection ? scene.selected_media : scene.original_video || scene.image
                    if (!selected || typeof selected !== 'object') return false
                    const metadata = selected.metadata || {}, video = hasSelection ? selected.asset_type === 'video' : !!scene.original_video
                    if (actual.kind !== (video ? 'original_video' : 'original_image') || (actual.source_asset_id ?? null) !== (selected.id ?? null)) return false
                    const expectedSha = metadata.render_sha256 || metadata.sha256
                    if (expectedSha && actual.media_sha256 !== expectedSha) return false
                    const storage = actual.source_storage || {}, path = metadata.gcs_path || metadata.storage_path, bucket = metadata.gcs_bucket || metadata.storage_bucket
                    if ((path && storage.gcs_path !== path) || (bucket && storage.gcs_bucket !== bucket)) return false
                }
                if (!Array.isArray(actual.frames) || !actual.frames.length || actual.frames.some((frame: any) =>
                    !hash(frame?.sha256) || !number(frame.seconds) || frame.seconds < 0 || frame.seconds >= scene.end - scene.start)) return false
            }
        }
        return true
    } catch { return false }
}
