import { createHash } from 'crypto'
import { supabaseAdmin } from './supabaseAdmin'
import { loadStdProject, runTts } from './stdTtsGenerate'
import { BACKGROUND_NARRATION_BATCH_SIZE } from './stdNarrationBatch'

export const ttsJobFingerprint = (body: any) => createHash('sha256').update(JSON.stringify(body)).digest('hex')
export const ttsSourceHash = (project: any) => ttsJobFingerprint([
    project.project_payload?.script, (project.project_payload?.subtitles || []).map((s: any) => [
        s.text, s.voice_id, s.voice_direction, s.voice_performance, s.dialogue_kind,
        s.dialogue_override, s.dialogue_speaker, s.editor_speaker?.name,
    ]),
    project.project_payload?.voice_id, project.project_payload?.tts_speed,
])
export function publicTtsJob(job: any) {
    if (!job) return null
    const { id, project_id, status, ready, total, reused, generated, error, updated_at } = job
    return { id, project_id, status, ready, total, reused, generated, error, updated_at }
}

// A database lease outlives the function timeout. Progress is checkpointed only
// after stored segments exist; interrupted slices safely reuse their recordings.
export async function processTtsJobs() {
    const { data, error } = await supabaseAdmin.rpc('claim_std_tts_job')
    if (error) throw error
    const job = data?.[0]
    if (!job) return { idle: true }
    const update = async (values: any) => {
        const result = await supabaseAdmin.from('std_tts_jobs').update({ ...values, updated_at: new Date().toISOString() })
            .eq('id', job.id).eq('lease_token', job.lease_token).select('id').single()
        if (result.error) throw result.error
    }
    try {
        const projectResult = await loadStdProject(job.project_id, job.owner_email)
        if (projectResult.error) throw projectResult.error
        const project = projectResult.data
        if (!project || project.employee_email !== job.owner_email) throw new Error('프로젝트 접근 권한이 변경되었습니다.')
        if (project.progress_payload?.background_tts_job_id === job.id && project.progress_payload?.subtitle_tts_completed) {
            await update({ status: 'completed', ready: job.total, result: { asset_id: project.progress_payload.tts_asset_id }, request: {}, lease_until: null, lease_token: null, error: null })
            return { recovered: job.id }
        }
        if (ttsSourceHash(project) !== job.source_hash) throw new Error('자막 또는 음성 설정이 변경되었습니다. 저장 후 TTS를 다시 요청해 주세요.')
        if (String(project.project_payload?.script || '') !== job.script) throw new Error('대본이 변경되었습니다. 자막을 저장하고 TTS를 다시 요청해 주세요.')
        const auth = { requester: { email: job.owner_email, user: { id: job.user_id } } }
        const call = async (body: any) => {
            const response = await runTts(body, auth, project, true, job.id)
            const payload = await response.json()
            if (!response.ok || payload.success === false) throw new Error(payload.error || '음성 처리 실패')
            return payload
        }
        const segments = job.request.voice_segments || []
        const deadline = Date.now() + 180_000
        while (job.ready < segments.length && Date.now() < deadline) {
            const batch = segments.slice(job.ready, job.ready + BACKGROUND_NARRATION_BATCH_SIZE)
            const payload = await call({ ...job.request, voice_segments: batch, text: batch.map((s: any) => s.text).join('\n'),
                mode: 'prepare_narration_segments', segment_offset: job.ready })
            if (payload.prepared !== batch.length) throw new Error('음성 구간 저장 결과가 일치하지 않습니다.')
            job.ready += batch.length
            job.reused += Number(payload.segment_reuse?.reused || 0)
            job.generated += Number(payload.segment_reuse?.generated || 0)
            job.attempts = 0
            await update({ ready: job.ready, reused: job.reused, generated: job.generated, attempts: 0, error: null })
        }
        if (job.ready >= segments.length && Date.now() < deadline) {
            const payload = await call({ ...job.request, mode: segments.length ? 'assemble_narration_segments' : undefined })
            if (!payload.asset?.id) throw new Error('최종 음성 저장을 확인하지 못했습니다.')
            await update({ status: 'completed', ready: job.total, result: { asset_id: payload.asset.id }, request: {}, lease_until: null, lease_token: null, error: null })
        } else {
            await update({ status: 'queued', lease_until: null, lease_token: null })
        }
    } catch (error: any) {
        const attempts = Number(job.attempts || 0) + 1
        await update({ status: attempts >= 3 ? 'failed' : 'queued', attempts,
            error: String(error?.message || error).slice(0, 500),
            next_run_at: new Date(Date.now() + attempts * 60_000).toISOString(), lease_until: null, lease_token: null })
    }
    return { processed: job.id }
}
