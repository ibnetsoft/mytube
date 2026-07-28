import { NextRequest } from 'next/server'
import { reportJobOutcome } from '@/lib/workerAuth'
import { supabaseAdmin } from '@/lib/supabaseAdmin'

export const dynamic = 'force-dynamic'

// [AIR-0230 §2d] script_plan_generate's whole purpose is landing its result
// on ONE specific topics_queue row (payload.topic_queue_id, validated
// required in worker/hermes_worker.py::_validate_script_plan_payload) - a
// result that only ever lives in remote_hermes_queue.result_payload is
// useless to claim_topic()/generate_script_structure_api(), which read
// topics_queue/project_settings, not the worker-protocol tables. This is a
// best-effort side effect: it must never change the response
// reportJobOutcome already decided (the worker's completion is final
// either way; a sync-back failure just means the buffer stays cold for
// this topic and the live AI-call path in
// app/routers/gemini.py::generate_script_structure_api() covers it as
// always).
async function syncPregeneratedStructure(jobId: string): Promise<void> {
    try {
        const { data: job } = await supabaseAdmin
            .from('remote_hermes_queue')
            .select('job_type, status, payload, result_payload')
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

        if (error) console.warn('[complete/route] pregenerated_structure sync-back update failed (non-fatal):', error.message)
    } catch (e) {
        console.warn('[complete/route] pregenerated_structure sync-back failed (non-fatal):', e)
    }
}

export async function POST(req: NextRequest, { params }: { params: { jobId: string } }) {
    const response = await reportJobOutcome(req, params.jobId, true)
    if (response.status === 200) {
        await syncPregeneratedStructure(params.jobId)
    }
    return response
}
