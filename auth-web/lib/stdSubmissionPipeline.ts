import { createHash, randomUUID } from 'crypto'
import { supabaseAdmin as db } from './supabaseAdmin'
import { aeMouthApplicable, aeMouthInput, currentAeMouthJob } from './stdAeMouth'
import { backgroundWindow } from './stdAudioMix'
import { sfxNeedsReview, resolveSfxCues } from './stdSfxCues'

export const SUBMISSION_PIPELINE_VERSION = 2
export function submissionSnapshot(project: any, scenes: any[], assets: any[], mouthRequired: boolean) {
    const frozen = JSON.parse(JSON.stringify({ project, scenes, assets }))
    frozen.project.project_payload = { ...frozen.project.project_payload, submission_pipeline_version: 2 }
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
    const mouth = mouthRequired ? aeMouthInput(frozen.project, scenes, assets) : {
        input: { project_id: project.id, scenes: [], subtitles: [], cast: {}, annotations: {} },
        fingerprint: createHash('sha256').update(`assembly:${project.id}:${project.updated_at}`).digest('hex'),
    }
    const previous = mouthRequired ? currentAeMouthJob(frozen.project, scenes, assets) : null
    const reusable = previous?.metadata?.fingerprint === mouth.fingerprint && previous.metadata?.pipeline_version === 2
        ? previous.metadata.results.filter((r: any) => r.status === 'artifact_ready') : []
    const outputIds = new Set(reusable.map((r: any) => r.asset_id))
    const audioIds = new Set([bgmId, ...enabled.map((c: any) => c.asset_id)])
    const selected = new Set<string>()
    // Freeze selected media and geometry, not every historical job's embedded input/results.
    frozen.assets = frozen.assets.filter((asset: any) => {
        if (outputIds.has(asset.id) || audioIds.has(asset.id) || asset.metadata?.kind === 'mouth_work_selection') return true
        if (['speaker_coordinate_confirmation','ae_speaker_coordinates','submitted_video_coordinates','eye_blink_confirmation'].includes(asset.metadata?.kind)) return true
        if (!['image','video','thumbnail','audio'].includes(asset.asset_type)) return false
        if (asset.metadata?.ae_mouth_fingerprint || asset.metadata?.lipsync_fingerprint) return false
        const key = `${asset.scene_number}:${asset.asset_type}`
        if (selected.has(key)) return false
        selected.add(key);return true
    })
    return { version: 2, ...frozen, mouth, reusable_results: reusable,
        failure_policy: { optional_composition: 'original', required_asset: 'input_error' } }
}

/** Final voice exists now: queue synced scene previews, without submitting a final render. */
export async function ensureSyncedMouthPreview(project: any, scenes: any[], assets: any[]) {
    if (!scenes.length) return null
    if (project.submitted_at || project.project_payload?.ae_mouth?.enabled === false || !aeMouthApplicable(project, scenes, assets)) return null
    const { input, fingerprint } = aeMouthInput(project, scenes, assets)
    const existing = assets.find(a => a.metadata?.kind === 'ae_mouth_job' && a.metadata.fingerprint === fingerprint && a.metadata.pipeline_version === 2)
    if (existing) {
        if (['failed','obsolete'].includes(existing.metadata.state)) {
            const updated = await db.from('std_project_assets').update({
                metadata: { ...existing.metadata, state: 'queued', phase: 'render', auto_pending: true,
                    technical_attempts: 0, error: null, results: existing.metadata.results.filter((r: any) => r.status === 'artifact_ready') },
                updated_at: new Date().toISOString(),
            }).eq('id', existing.id).eq('updated_at', existing.updated_at).select('*').maybeSingle()
            if (updated.error) throw updated.error
            return updated.data || existing
        }
        return existing
    }
    const path = `std/${project.id}/mouth-preview-v2/${fingerprint}.json`
    const claim = await db.storage.from('content-assets').upload(path, Buffer.from(JSON.stringify({ fingerprint })), { contentType: 'application/json', upsert: false })
    if (claim.error) {
        if (/already exists|duplicate/i.test(claim.error.message)) return null
        throw claim.error
    }
    const inserted = await db.from('std_project_assets').insert({ project_id: project.id, asset_type: 'other', status: 'uploaded',
        file_name: `synced-mouth-${fingerprint}.json`, mime_type: 'application/json',
        metadata: { kind: 'ae_mouth_job', pipeline_version: 2, preview_sync: true,
            state: 'queued', phase: 'render', automatic: true, auto_pending: true,
            auto_video_coordinates: false, fingerprint, input, results: [] },
    }).select('*').single()
    if (inserted.error) { await db.storage.from('content-assets').remove([path]); throw inserted.error }
    return inserted.data
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
