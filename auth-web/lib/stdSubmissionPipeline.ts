import { createHash, randomUUID } from 'crypto'
import { supabaseAdmin as db } from './supabaseAdmin'
import { aeMouthApplicable, aeMouthInput, currentAeMouthJob } from './stdAeMouth'
import { backgroundWindow } from './stdAudioMix'
import { sfxNeedsReview, resolveSfxCues } from './stdSfxCues'
import { assertPreparationFinished, assertPreparedMouthGeometry } from './stdWorkflowBoundary'
import { hasAeSceneIntent } from './stdAeScenePreparation'
import { aeSceneArtifactReviewMatches, aeSceneRenderReviewMatches } from './stdAeSceneReview'

export const SUBMISSION_PIPELINE_VERSION = 2
export function submissionSnapshot(project: any, scenes: any[], assets: any[], mouthRequired: boolean) {
    assertPreparationFinished(assets)
    const frozen = JSON.parse(JSON.stringify({ project, scenes, assets }))
    frozen.project.project_payload = { ...frozen.project.project_payload, submission_pipeline_version: 2 }
    mouthRequired = mouthRequired || hasAeSceneIntent(frozen.project, frozen.scenes, frozen.assets)
    const settings = { ...frozen.project.project_payload.settings, ...frozen.project.project_payload.render_settings }
    const bgmId = settings.bgm_asset_id || frozen.project.project_payload.bgm_asset_id
    const subtitles = frozen.project.project_payload.subtitles || []
    const end = Math.max(0, ...subtitles.map((r: any) => Number(r.end_num ?? r.end_time ?? r.end) || 0))
    if (bgmId && !backgroundWindow(settings, subtitles, end).valid)
        throw new Error('배경음 시작·종료 자막을 확인해 주세요. 저장된 구간을 찾을 수 없습니다.')
    const enabled = (settings.sfx_cues || frozen.project.project_payload.sfx_cues || []).filter((c: any) => c.enabled !== false)
    for (const cue of enabled) {
        if (sfxNeedsReview(cue, subtitles) || (!cue.library_key && !assets.some((a: any) => a.id === cue.asset_id)))
            throw new Error('효과음 파일 또는 자막 앵커를 확인해 주세요.')
    }
    if (bgmId && !assets.some((a: any) => a.id === bgmId))
        throw new Error('선택한 배경음 파일이 없습니다.')
    const mouth = mouthRequired ? aeMouthInput(frozen.project, frozen.scenes, frozen.assets) : {
        input: { project_id: project.id, scenes: [], subtitles: [], cast: {}, annotations: {} },
        fingerprint: createHash('sha256').update(`assembly:${project.id}:${project.updated_at}`).digest('hex'),
    }
    if(mouthRequired)assertPreparedMouthGeometry(mouth.input)
    const previous = mouthRequired ? currentAeMouthJob(frozen.project, scenes, assets) : null
    if (mouthRequired) frozen.project.project_payload.ae_mouth = { ...frozen.project.project_payload.ae_mouth, enabled: true }
    const reusable = previous?.metadata?.fingerprint === mouth.fingerprint && previous.metadata?.pipeline_version === 2
        ? previous.metadata.results.filter((row: any) => {
            if (row.status !== 'artifact_ready') return false
            const scene = mouth.input.scenes.find((scene: any) => scene.number === row.number)
            if (!scene) return false
            if (!scene.ae_scene) return true
            const asset = assets.find((asset: any) => asset.id === row.asset_id && asset.asset_type === 'video' &&
                ['uploaded', 'assigned'].includes(asset.status) && Number(asset.scene_number) === scene.number)
            return asset?.metadata?.artifact_ready === true && asset.metadata.timing_locked === true &&
                asset.metadata.source_audio_id === (mouth.input as any).audio.id && asset.metadata.render_sha256 === row.render_sha256 &&
                asset.metadata.ae_mouth_fingerprint === mouth.fingerprint && asset.metadata.voice_synced !== false &&
                Math.abs(Number(asset.metadata.duration_seconds) - (scene.end - scene.start)) <= .12 &&
                aeSceneArtifactReviewMatches(scene, (mouth.input as any).audio, asset.metadata) &&
                aeSceneRenderReviewMatches(scene, (mouth.input as any).audio, row.output_review, row.render_sha256)
        }) : []
    const outputIds = new Set(reusable.map((r: any) => r.asset_id))
    const sourceIds = new Set<string>()
    const narrationId = (mouth.input as any).audio?.id
    if (narrationId) sourceIds.add(narrationId)
    for (const scene of [...(mouth.input.scenes || []), ...((mouth.input as any).sequence_scenes || [])] as any[]) {
        for (const source of [scene.image, scene.original_video, scene.selected_media, scene.ae_scene, scene.ae_scene?.metadata?.input?.source_psd]) {
            if (source?.id) sourceIds.add(source.id)
        }
    }
    const audioIds = new Set([bgmId, ...enabled.map((c: any) => c.asset_id)])
    const frozenVisualKeys = new Set(frozen.assets.filter((asset: any) => sourceIds.has(asset.id) &&
        ['image', 'video'].includes(asset.asset_type)).map((asset: any) => `${asset.scene_number}:${asset.asset_type}`))
    const selected = new Set<string>()
    // Freeze selected media and geometry, not every historical job's embedded input/results.
    frozen.assets = frozen.assets.filter((asset: any) => {
        if (sourceIds.has(asset.id) || outputIds.has(asset.id) || audioIds.has(asset.id) || asset.metadata?.kind === 'mouth_work_selection') return true
        if (narrationId && asset.asset_type === 'audio') return false
        if (['speaker_coordinate_confirmation','ae_speaker_coordinates','submitted_video_coordinates','eye_blink_confirmation'].includes(asset.metadata?.kind)) return true
        if (!['image','video','thumbnail','audio'].includes(asset.asset_type)) return false
        if (asset.metadata?.ae_mouth_fingerprint || asset.metadata?.lipsync_fingerprint) return false
        const key = `${asset.scene_number}:${asset.asset_type}`
        if (frozenVisualKeys.has(key)) return false
        if (selected.has(key)) return false
        selected.add(key);return true
    })
    return { version: 2, ...frozen, mouth, reusable_results: reusable,
        failure_policy: { optional_composition: 'original', required_asset: 'input_error' } }
}

/** Final voice exists now: queue synced scene previews, without submitting a final render. */
export async function ensureSyncedMouthPreview(_project: any, _scenes: any[], _assets: any[]) {
    return null
}

export async function registerSubmissionPipeline(project: any, scenes: any[], assets: any[], userId: string, mouthRequired: boolean) {
    const manifest = submissionSnapshot(project, scenes, assets, mouthRequired)
    const runId = randomUUID(), jobId = randomUUID()
    const hash = createHash('sha256').update(JSON.stringify(manifest)).digest('hex')
    const result = await db.rpc('register_std_pipeline', {
        p_project_id: project.id, p_user_id: userId, p_updated_at: project.updated_at,
        p_run_id: runId, p_job_id: jobId, p_manifest: manifest, p_hash: hash,
    })
    if (result.error) throw result.error
    return result.data
}

export async function frozenRenderBundle(projectId: string, jobId: string) {
    const job = await db.from('std_project_assets').select('*').eq('id', jobId).eq('project_id', projectId).single()
    if (job.error) throw job.error
    if (job.data.metadata?.pipeline_version !== 2) return null
    const run = await db.from('std_pipeline_runs').select('*').eq('id', job.data.metadata.pipeline_run_id).eq('project_id', projectId).single()
    if (run.error) throw run.error
    if (run.data.job_id !== jobId) throw new Error('Submission job does not match its frozen run')
    const manifest = run.data.manifest
    const ids = (job.data.metadata.results || []).map((r: any) => r.asset_id).filter(Boolean)
    const outputs = ids.length ? await db.from('std_project_assets').select('*').eq('project_id', projectId).in('id', ids) : { data: [], error: null }
    if (outputs.error) throw outputs.error
    return { project: { ...manifest.project, progress_payload: { ...manifest.project.progress_payload, pipeline_run_id: run.data.id } },
        scenes: manifest.scenes, assets: [...manifest.assets.filter((a: any) => a.id !== jobId), job.data, ...(outputs.data || [])] }
}
