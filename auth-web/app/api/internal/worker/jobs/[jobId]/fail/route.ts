import { NextRequest } from 'next/server'
import { reportJobOutcome } from '@/lib/workerAuth'
import { supabaseAdmin } from '@/lib/supabaseAdmin'

export const dynamic = 'force-dynamic'

// [AIR-0230 §2d] Mirrors complete/route.ts's sync-back - without this, a
// failed script_plan_generate/script_generate job leaves
// topics_queue.pregenerated_structure_status/pregenerated_script_status
// stuck at 'queued' forever, which would make a future buffer-fill pass
// think this topic is still being worked on and skip re-enqueueing it.
async function markPregeneratedFailed(jobId: string): Promise<void> {
    try {
        const { data: job } = await supabaseAdmin
            .from('remote_hermes_queue')
            .select('job_type, status, payload')
            .eq('id', jobId)
            .maybeSingle()

        if (!job || job.status !== 'failed') return

        const topicQueueId = job.payload?.topic_queue_id
        if (!topicQueueId) return

        if (job.job_type === 'script_plan_generate') {
            const { error } = await supabaseAdmin
                .from('topics_queue')
                .update({ pregenerated_structure_status: 'failed' })
                .eq('id', topicQueueId)
            if (error) console.warn('[fail/route] pregenerated_structure_status update failed (non-fatal):', error.message)
        } else if (job.job_type === 'script_generate') {
            const { error } = await supabaseAdmin
                .from('topics_queue')
                .update({ pregenerated_script_status: 'failed' })
                .eq('id', topicQueueId)
            if (error) console.warn('[fail/route] pregenerated_script_status update failed (non-fatal):', error.message)
        }
    } catch (e) {
        console.warn('[fail/route] pregenerated status sync failed (non-fatal):', e)
    }
}

export async function POST(req: NextRequest, { params }: { params: { jobId: string } }) {
    const response = await reportJobOutcome(req, params.jobId, false)
    if (response.status === 200) {
        await markPregeneratedFailed(params.jobId)
    }
    return response
}
