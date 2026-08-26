import { NextRequest } from 'next/server'
import { reportJobOutcome } from '@/lib/workerAuth'
import { supabaseAdmin } from '@/lib/supabaseAdmin'

export const dynamic = 'force-dynamic'

function stripGeneratedPlanningText(rawScriptText: string | null | undefined): string {
    const text = String(rawScriptText || '').trim()
    if (!text) return ''

    return text
        .split(/\n\s*\n+/)
        .map(part => part.trim())
        .filter(part => {
            if (!part) return false
            return !(
                /\d+\s*\uBC88\uC9F8\s*\uC7A5\uBA74/.test(part)
                || /Opening beat/i.test(part)
                || /Create immediate/i.test(part)
                || /Leave one story secret/i.test(part)
                || /unresolved into the next beat/i.test(part)
                || /Reference technique from benchmark/i.test(part)
                || /Timed\s+\w+\s+visual beat/i.test(part)
            )
        })
        .join('\n\n')
        .trim()
}

// [AIR-0230 §2d] script_plan_generate/script_generate's whole purpose is
// landing their result on ONE specific topics_queue row
// (payload.topic_queue_id, validated required in
// worker/hermes_worker.py::_validate_script_plan_payload /
// _validate_script_generate_payload) - a result that only ever lives in
// remote_hermes_queue.result_payload is useless to
// claim_topic()/generate_script_structure_api(), which read
// topics_queue/project_settings, not the worker-protocol tables. Both
// syncs are best-effort side effects: they must never change the response
// reportJobOutcome already decided.
async function syncPregeneratedStructure(jobId: string): Promise<void> {
    try {
        const { data: job } = await supabaseAdmin
            .from('remote_hermes_queue')
            .select('job_type, status, payload, result_payload, category_id, worker_id, worker_instance_id, target_worker_id')
            .eq('id', jobId)
            .maybeSingle()

        if (!job || job.status !== 'completed' || job.job_type !== 'script_plan_generate') return

        const topicQueueId = job.payload?.topic_queue_id
        const structure = job.result_payload?.structure
        if (!topicQueueId || !structure) return
        const selectedImageStyle = String(
            job.result_payload?.image_style || structure?.image_style || ''
        ).trim()
        const rawImageStyleSelection = job.result_payload?.image_style_selection || structure?.image_style_selection || null
        const imageStyleSelection = rawImageStyleSelection && typeof rawImageStyleSelection === 'object'
            ? rawImageStyleSelection
            : null
        const updatePayload: Record<string, any> = {
            pregenerated_structure: structure,
            pregenerated_structure_status: 'ready',
        }
        if (job.worker_id) {
            updatePayload.generated_by_worker_id = job.worker_id
            updatePayload.generated_by_worker_instance_id = job.worker_instance_id || null
            updatePayload.generated_by_worker_job_id = jobId
            updatePayload.generated_by_worker_at = new Date().toISOString()
        }
        if (selectedImageStyle) {
            updatePayload.assigned_image_style = selectedImageStyle
        }
        if (imageStyleSelection) {
            const existingBenchmark = job.payload?.benchmark_analysis || {}
            updatePayload.benchmark_analysis = {
                ...(existingBenchmark && typeof existingBenchmark === 'object' ? existingBenchmark : {}),
                image_style_selection: imageStyleSelection,
            }
            if (
                !updatePayload.benchmark_analysis.image_style_selection.assigned_image_style
                && selectedImageStyle
            ) {
                updatePayload.benchmark_analysis.image_style_selection.assigned_image_style = selectedImageStyle
            }
        }

        const { error } = await supabaseAdmin
            .from('topics_queue')
            .update(updatePayload)
            .eq('id', topicQueueId)

        if (error) {
            console.warn('[complete/route] pregenerated_structure sync-back update failed (non-fatal):', error.message)
            return
        }

        // [AIR-0230 §2d chaining] The buffer's whole point is "topic -> plan
        // -> script all pre-baked before claim" - a ready structure with no
        // follow-up script_generate job would leave the buffer permanently
        // stuck at "planned but not scripted". script_generate needs the
        // structure as input (payload.structure), which is only available
        // now that this job has completed - so this is the one point where
        // enqueueing it makes sense, not at topic-generation time alongside
        // script_plan_generate (the structure wouldn't exist yet then).
        const jobPayload = job.payload || {}
        const { error: enqueueError } = await supabaseAdmin
            .from('remote_hermes_queue')
            .insert({
                job_type: 'script_generate',
                target_worker_id: job.worker_id || job.target_worker_id || null,
                // [FIX] category_id is a top-level remote_hermes_queue column,
                // never part of payload (see the script_plan_generate insert in
                // auth-web/app/api/admin/topics-queue/route.ts) - reading
                // jobPayload.category_id here always evaluated to undefined,
                // so every chain-enqueued script_generate job silently got
                // category_id: null. Harmless today (nothing currently queries
                // script_plan_generate/script_generate rows by category_id,
                // unlike topic_benchmark_analyze's freshness check), but wrong
                // data - fixed to read the actual row column.
                category_id: job.category_id ?? null,
                payload: {
                    topic_queue_id: String(topicQueueId),
                    topic: jobPayload.topic,
                    structure,
                    script_style: jobPayload.script_style,
                    image_style: selectedImageStyle || jobPayload.image_style,
                    image_style_selection: imageStyleSelection || jobPayload.image_style_selection,
                    language: jobPayload.language,
                    target_duration_seconds: jobPayload.target_duration_seconds,
                    upload_title: job.result_payload?.upload_title || jobPayload.upload_title,
                    title_generation: job.result_payload?.title_generation || jobPayload.title_generation,
                    narration_mode: jobPayload.narration_mode || 'dramatic_single',
                    narration_pace: jobPayload.narration_pace || 'senior',
                    target_scene_count: jobPayload.target_scene_count,
                    repair_mode: jobPayload.repair_mode,
                    repair_instruction: jobPayload.repair_instruction,
                    repair_source_script: jobPayload.repair_source_script,
                },
                status: 'pending',
            })
        if (enqueueError) console.warn('[complete/route] Failed to chain-enqueue script_generate (non-fatal):', enqueueError.message)

        await supabaseAdmin
            .from('topics_queue')
            .update({ pregenerated_script_status: 'queued' })
            .eq('id', topicQueueId)
    } catch (e) {
        console.warn('[complete/route] pregenerated_structure sync-back failed (non-fatal):', e)
    }
}

async function syncPregeneratedScript(jobId: string): Promise<void> {
    try {
        const { data: job } = await supabaseAdmin
            .from('remote_hermes_queue')
            .select('job_type, status, payload, result_payload, category_id, worker_id, worker_instance_id, target_worker_id')
            .eq('id', jobId)
            .maybeSingle()

        if (!job || job.status !== 'completed' || job.job_type !== 'script_generate') return

        const topicQueueId = job.payload?.topic_queue_id
        const script = stripGeneratedPlanningText(job.result_payload?.script)
        if (!topicQueueId || !script) return

        const resultPayload = job.result_payload || {}
        const { data: existingTopic } = await supabaseAdmin
            .from('topics_queue')
            .select('progress_payload')
            .eq('id', topicQueueId)
            .maybeSingle()
        const existingProgress = existingTopic?.progress_payload && typeof existingTopic.progress_payload === 'object'
            ? existingTopic.progress_payload
            : {}
        const sfxCues = Array.isArray(resultPayload.sfx_cues)
            ? resultPayload.sfx_cues
            : Array.isArray(existingProgress.sfx_cues)
                ? existingProgress.sfx_cues
                : []
        const sfxCuesJson = resultPayload.sfx_cues_json || existingProgress.sfx_cues_json || JSON.stringify(sfxCues)
        const progressPayload = {
            ...existingProgress,
            publish_metadata: resultPayload.publish_metadata || existingProgress.publish_metadata || null,
            sfx_cues: sfxCues,
            sfx_cues_json: sfxCuesJson,
            pregenerated_script_status: 'ready',
            ...(resultPayload.structure ? { pregenerated_structure_status: 'ready' } : {}),
            prepared_topic_ready: true,
            prepared_topic_ready_at: new Date().toISOString(),
        }
        let { error } = await supabaseAdmin
            .from('topics_queue')
            .update({
                pregenerated_script: script,
                pregenerated_script_status: 'ready',
                ...(resultPayload.structure ? {
                    pregenerated_structure: resultPayload.structure,
                    pregenerated_structure_status: 'ready',
                    total_scenes: Array.isArray(resultPayload.structure?.scenes)
                        ? resultPayload.structure.scenes.length
                        : resultPayload.structure?.scene_count || null,
                } : {}),
                ...(resultPayload.publish_metadata ? { publish_metadata: resultPayload.publish_metadata } : {}),
                progress_payload: progressPayload,
                narrative_blueprint: resultPayload.narrative_blueprint || null,
                script_quality_report: resultPayload.script_quality_report || null,
                ...(job.worker_id ? {
                    generated_by_worker_id: job.worker_id,
                    generated_by_worker_instance_id: job.worker_instance_id || null,
                    generated_by_worker_job_id: jobId,
                    generated_by_worker_at: new Date().toISOString(),
                } : {}),
            })
            .eq('id', topicQueueId)

        if (error) {
            const fallback = await supabaseAdmin
                .from('topics_queue')
                .update({
                    pregenerated_script: script,
                    pregenerated_script_status: 'ready',
                    progress_payload: progressPayload,
                })
                .eq('id', topicQueueId)
            error = fallback.error
        }
        if (error) console.warn('[complete/route] pregenerated_script sync-back update failed (non-fatal):', error.message)
        const jobPayload = job.payload || {}
        const { error: enqueueError } = await supabaseAdmin
            .from('remote_hermes_queue')
            .insert({
                job_type: 'publish_metadata_generate',
                target_worker_id: job.worker_id || job.target_worker_id || null,
                category_id: job.category_id ?? null,
                payload: {
                    topic_queue_id: String(topicQueueId),
                    topic: resultPayload.topic || jobPayload.topic,
                    script,
                    structure: resultPayload.structure || jobPayload.structure || {},
                    upload_title: resultPayload.upload_title || jobPayload.upload_title,
                    title_generation: resultPayload.title_generation || jobPayload.title_generation,
                    narrative_blueprint: resultPayload.narrative_blueprint || {},
                    script_quality_report: resultPayload.script_quality_report || {},
                    sfx_cues: sfxCues,
                    sfx_cues_json: sfxCuesJson,
                    defer_ready_until_quality_gate: Boolean(jobPayload.defer_ready_until_quality_gate),
                    language: jobPayload.language,
                },
                status: 'pending',
            })
        if (enqueueError) console.warn('[complete/route] Failed to chain-enqueue publish_metadata_generate (non-fatal):', enqueueError.message)
        await supabaseAdmin
            .from('topics_queue')
            .update({ publish_metadata_status: 'queued' })
            .eq('id', topicQueueId)
        await recordContentGenerationFeedback(jobId, job, topicQueueId, script)
    } catch (e) {
        console.warn('[complete/route] pregenerated_script sync-back failed (non-fatal):', e)
    }
}

async function syncPublishMetadata(jobId: string): Promise<void> {
    try {
        const { data: job } = await supabaseAdmin
            .from('remote_hermes_queue')
            .select('job_type, status, payload, result_payload, worker_id, worker_instance_id')
            .eq('id', jobId)
            .maybeSingle()

        if (!job || job.status !== 'completed' || job.job_type !== 'publish_metadata_generate') return

        const topicQueueId = job.payload?.topic_queue_id
        const resultPayload = job.result_payload || {}
        const publishMetadata = resultPayload.publish_metadata
        if (!topicQueueId || !publishMetadata) return
        const structure = resultPayload.structure && typeof resultPayload.structure === 'object'
            ? resultPayload.structure
            : null
        const script = typeof resultPayload.script === 'string' ? stripGeneratedPlanningText(resultPayload.script) : ''
        const sceneCount = Array.isArray(structure?.scenes)
            ? structure.scenes.length
            : structure?.scene_count || null

        const { data: existingTopic } = await supabaseAdmin
            .from('topics_queue')
            .select('progress_payload')
            .eq('id', topicQueueId)
            .maybeSingle()
        const existingProgress = existingTopic?.progress_payload && typeof existingTopic.progress_payload === 'object'
            ? existingTopic.progress_payload
            : {}
        const sfxCues = Array.isArray(resultPayload.sfx_cues)
            ? resultPayload.sfx_cues
            : Array.isArray(existingProgress.sfx_cues)
                ? existingProgress.sfx_cues
                : []
        const sfxCuesJson = resultPayload.sfx_cues_json || existingProgress.sfx_cues_json || JSON.stringify(sfxCues)
        const progressPayload = {
            ...existingProgress,
            publish_metadata: publishMetadata,
            sfx_cues: sfxCues,
            sfx_cues_json: sfxCuesJson,
            publish_metadata_status: 'ready',
            pregenerated_script_status: script ? 'ready' : existingProgress.pregenerated_script_status,
            pregenerated_structure_status: structure ? 'ready' : existingProgress.pregenerated_structure_status,
            prepared_topic_ready: true,
            prepared_topic_ready_at: new Date().toISOString(),
        }

        const updatePayload: Record<string, any> = {
            status: 'pending',
            publish_metadata: publishMetadata,
            publish_metadata_status: 'ready',
            progress_payload: progressPayload,
        }
        if (script) {
            updatePayload.pregenerated_script = script
            updatePayload.pregenerated_script_status = 'ready'
        }
        if (structure) {
            updatePayload.pregenerated_structure = structure
            updatePayload.pregenerated_structure_status = 'ready'
        }
        if (sceneCount) updatePayload.total_scenes = sceneCount
        if (resultPayload.generated_title || resultPayload.upload_title) {
            updatePayload.generated_title = resultPayload.generated_title || resultPayload.upload_title
        }
        if (resultPayload.narrative_blueprint) updatePayload.narrative_blueprint = resultPayload.narrative_blueprint
        if (resultPayload.script_quality_report) updatePayload.script_quality_report = resultPayload.script_quality_report
        if (job.worker_id) {
            updatePayload.generated_by_worker_id = job.worker_id
            updatePayload.generated_by_worker_instance_id = job.worker_instance_id || null
            updatePayload.generated_by_worker_job_id = jobId
            updatePayload.generated_by_worker_at = new Date().toISOString()
        }

        let { error } = await supabaseAdmin
            .from('topics_queue')
            .update(updatePayload)
            .eq('id', topicQueueId)

        if (error) {
            const fallbackPayload = { ...updatePayload }
            delete fallbackPayload.narrative_blueprint
            delete fallbackPayload.script_quality_report
            const fallback = await supabaseAdmin
                .from('topics_queue')
                .update(fallbackPayload)
                .eq('id', topicQueueId)
            error = fallback.error
        }

        if (error) {
            const fallback = await supabaseAdmin
                .from('topics_queue')
                .update({
                    publish_metadata: publishMetadata,
                    progress_payload: progressPayload,
                })
                .eq('id', topicQueueId)
            error = fallback.error
        }
        if (error) console.warn('[complete/route] publish_metadata sync-back update failed (non-fatal):', error.message)
    } catch (e) {
        console.warn('[complete/route] publish_metadata sync-back failed (non-fatal):', e)
    }
}

function clampScore(value: number): number {
    if (!Number.isFinite(value)) return 0
    return Math.max(0, Math.min(100, Math.round(value * 100) / 100))
}

function scoreGeneratedTitle(title: string, titleGeneration: any): { score: number; reasons: string[] } {
    let score = 70
    const reasons: string[] = []
    const cleanTitle = String(title || '').trim()
    const forbiddenTerms = [
        '성공 공식', '스토리텔링', '벤치마킹', '패턴', '알고리즘',
        '콘텐츠', '조회수', '분석', '전략', '공식', '노하우', '비법', '비밀', '비결', '해부',
        '황금률', '치트키', '필독', '마스터', '명작', '망작', '시청자', '대공개', '법칙',
        '불문율', '반전 사연', '반전 스토리',
    ]

    if (!cleanTitle) {
        return { score: 0, reasons: ['missing_title'] }
    }

    if (cleanTitle.length >= 28 && cleanTitle.length <= 58) {
        score += 10
        reasons.push('good_length')
    } else {
        score -= Math.min(25, Math.abs(43 - cleanTitle.length))
        reasons.push('length_penalty')
    }

    const matchedForbidden = forbiddenTerms.filter(term => cleanTitle.includes(term))
    if (matchedForbidden.length) {
        score -= 35 + matchedForbidden.length * 5
        reasons.push('meta_or_report_like_terms')
    }

    const selectedScore = Number(titleGeneration?.selected_score)
    if (Number.isFinite(selectedScore)) {
        score = score * 0.65 + selectedScore * 0.35
        reasons.push('generator_score_blended')
    }

    const fitStatus = titleGeneration?.script_fit?.status
    if (fitStatus === 'pass') {
        score += 8
        reasons.push('script_fit_pass')
    } else if (fitStatus === 'revise') {
        score -= 10
        reasons.push('script_fit_revised')
    }

    return { score: clampScore(score), reasons }
}

function scoreGeneratedScript(script: string, resultPayload: any): { score: number; reasons: string[] } {
    let score = 70
    const reasons: string[] = []
    const text = String(script || '').trim()
    const charCount = Number(resultPayload?.char_count || text.length)
    const qaScore = Number(resultPayload?.script_quality_report?.score)

    if (!text) return { score: 0, reasons: ['missing_script'] }

    if (charCount >= 3500) {
        score += 10
        reasons.push('longform_length_ok')
    } else {
        score -= 20
        reasons.push('short_script_penalty')
    }

    if (text.includes('스토리텔링') || text.includes('콘텐츠') || text.includes('분석')) {
        score -= 12
        reasons.push('meta_language_in_script')
    }

    if (resultPayload?.upload_title) {
        score += 5
        reasons.push('has_upload_title_contract')
    }

    if (Number.isFinite(qaScore)) {
        score = score * 0.35 + qaScore * 0.65
        reasons.push('worker_story_qa_blended')
    }

    return { score: clampScore(score), reasons }
}

function qualityFromScores(titleScore: number, scriptScore: number): string {
    const blended = titleScore * 0.45 + scriptScore * 0.55
    if (blended >= 85) return 'excellent'
    if (blended >= 72) return 'good'
    if (blended >= 55) return 'neutral'
    return 'poor'
}

async function recordContentGenerationFeedback(jobId: string, job: any, topicQueueId: any, script: string): Promise<void> {
    try {
        const resultPayload = job.result_payload || {}
        const titleGeneration = resultPayload.title_generation || {}
        const uploadTitle = String(resultPayload.upload_title || titleGeneration.generated_title || '').trim()
        const titleScore = scoreGeneratedTitle(uploadTitle, titleGeneration)
        const scriptScore = scoreGeneratedScript(script, resultPayload)

        const { data: topicRow } = await supabaseAdmin
            .from('topics_queue')
            .select('id, topic, category_id, generated_title, title_candidates, benchmark_analysis, categories(name)')
            .eq('id', topicQueueId)
            .maybeSingle()

        const categories = (topicRow as any)?.categories
        const categoryName = Array.isArray(categories)
            ? categories[0]?.name
            : categories?.name

        const row = {
            topic_queue_id: String(topicQueueId),
            category_id: String(topicRow?.category_id || job.category_id || ''),
            category_name: categoryName || null,
            source_job_id: jobId,
            feedback_source: 'auto',
            outcome_quality: qualityFromScores(titleScore.score, scriptScore.score),
            generated_title: uploadTitle || topicRow?.generated_title || null,
            production_topic: resultPayload.topic || topicRow?.topic || null,
            title_score: titleScore.score,
            script_score: scriptScore.score,
            metrics: {
                char_count: resultPayload.char_count || String(script || '').length,
                read_time_seconds: resultPayload.read_time_seconds,
                narration_mode: resultPayload.narration_mode,
                revision_count: resultPayload.revision_count || 0,
                title_score_reasons: titleScore.reasons,
                script_score_reasons: scriptScore.reasons,
            },
            title_generation: titleGeneration || {},
            benchmark_summary: {
                benchmark_analysis: topicRow?.benchmark_analysis || null,
                audit_summary: topicRow?.benchmark_analysis?.audit_summary || null,
            },
            evaluation: {
                type: 'auto_heuristic_v1',
                title_score: titleScore,
                script_score: scriptScore,
                worker_script_quality_report: resultPayload.script_quality_report || null,
                narrative_blueprint: resultPayload.narrative_blueprint || null,
                learning_profile: resultPayload.learning_profile || null,
            },
            updated_at: new Date().toISOString(),
        }

        const { error } = await supabaseAdmin
            .from('content_generation_feedback')
            .upsert(row, { onConflict: 'topic_queue_id,feedback_source' })

        if (error) {
            console.warn('[complete/route] content_generation_feedback insert failed (non-fatal):', error.message)
        }
    } catch (e) {
        console.warn('[complete/route] content_generation_feedback sync failed (non-fatal):', e)
    }
}

export async function POST(req: NextRequest, { params }: { params: { jobId: string } }) {
    const response = await reportJobOutcome(req, params.jobId, true)
    if (response.status === 200) {
        await syncPregeneratedStructure(params.jobId)
        await syncPregeneratedScript(params.jobId)
        await syncPublishMetadata(params.jobId)
    }
    return response
}
