import { NextRequest } from 'next/server'
import { reportJobOutcome } from '@/lib/workerAuth'
import { supabaseAdmin } from '@/lib/supabaseAdmin'

export const dynamic = 'force-dynamic'

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
            .select('job_type, status, payload, result_payload, category_id')
            .eq('id', jobId)
            .maybeSingle()

        if (!job || job.status !== 'completed' || job.job_type !== 'script_plan_generate') return

        const topicQueueId = job.payload?.topic_queue_id
        const structure = job.result_payload?.structure
        if (!topicQueueId || !structure) return

        const { error } = await supabaseAdmin
            .from('topics_queue')
            .update({
                pregenerated_structure: structure,
                pregenerated_structure_status: 'ready',
            })
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
                    language: jobPayload.language,
                    target_duration_seconds: jobPayload.target_duration_seconds,
                    // narration_mode has no per-topic source yet - defaults
                    // to 'single' in worker/hermes_worker.py's payload
                    // validation, matching the safer/more common default.
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
            .select('job_type, status, payload, result_payload')
            .eq('id', jobId)
            .maybeSingle()

        if (!job || job.status !== 'completed' || job.job_type !== 'script_generate') return

        const topicQueueId = job.payload?.topic_queue_id
        const script = job.result_payload?.script
        if (!topicQueueId || !script) return

        const { error } = await supabaseAdmin
            .from('topics_queue')
            .update({
                pregenerated_script: script,
                pregenerated_script_status: 'ready',
            })
            .eq('id', topicQueueId)

        if (error) console.warn('[complete/route] pregenerated_script sync-back update failed (non-fatal):', error.message)
    } catch (e) {
        console.warn('[complete/route] pregenerated_script sync-back failed (non-fatal):', e)
    }
}

export async function POST(req: NextRequest, { params }: { params: { jobId: string } }) {
    const response = await reportJobOutcome(req, params.jobId, true)
    if (response.status === 200) {
        await syncPregeneratedStructure(params.jobId)
        await syncPregeneratedScript(params.jobId)
    }
    return response
}
