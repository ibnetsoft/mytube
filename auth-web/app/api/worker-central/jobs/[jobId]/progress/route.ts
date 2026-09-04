import { NextRequest, NextResponse } from 'next/server'
import { supabaseAdmin } from '@/lib/supabaseAdmin'
import { authenticateWorkerRequest, readJsonBodyWithLimit, isHermesJobId } from '@/lib/workerAuth'

export const dynamic = 'force-dynamic'

const VALID_STATUSES = new Set(['CLAIMED', 'PREPARING', 'RENDERING', 'UPLOADING'])

export async function POST(req: NextRequest, { params }: { params: { jobId: string } }) {
    const auth = await authenticateWorkerRequest(req)
    if (!auth.ok) return auth.response

    const bodyResult = await readJsonBodyWithLimit(req)
    if (!bodyResult.ok) return bodyResult.response
    const { lease_id, worker_instance_id, worker_status, progress, message } = bodyResult.body || {}

    if (!lease_id || !worker_instance_id || !worker_status) {
        return NextResponse.json({ error: 'invalid_request', detail: 'lease_id, worker_instance_id and worker_status are required' }, { status: 400 })
    }
    if (!VALID_STATUSES.has(worker_status)) {
        return NextResponse.json({ error: 'invalid_request', detail: `worker_status must be one of ${[...VALID_STATUSES].join(', ')}` }, { status: 400 })
    }
    const progressNum = Number(progress)
    if (!Number.isFinite(progressNum) || progressNum < 0 || progressNum > 100) {
        return NextResponse.json({ error: 'invalid_request', detail: 'progress must be a number between 0 and 100' }, { status: 400 })
    }

    // [AIR-0230] see claim/route.ts's comment - table/RPC choice is derived
    // from the authenticated worker's job-type family, not request input.
    let hermes: boolean
    try {
        hermes = await isHermesJobId(params.jobId)
    } catch (error) {
        return NextResponse.json({ error: 'db_error', detail: String(error) }, { status: 500 })
    }
    const { data, error } = await supabaseAdmin.rpc(
        hermes ? 'report_worker_hermes_job_progress' : 'report_worker_render_job_progress',
        {
            p_job_id: params.jobId,
            p_lease_id: lease_id,
            p_worker_instance_id: worker_instance_id,
            p_worker_status: worker_status,
            p_progress: progressNum,
            p_message: typeof message === 'string' ? message.slice(0, 500) : null,
        }
    )

    if (error) return NextResponse.json({ error: 'db_error', detail: error.message }, { status: 500 })

    const job = Array.isArray(data) ? data[0] : data
    if (!job) {
        // Either the lease doesn't match (stale/reassigned) or the requested
        // worker_status is not a valid transition from the job's current
        // worker_status - the RPC can't distinguish these for the caller
        // without a second round trip, and both are legitimately 409s.
        return NextResponse.json({ error: 'conflict', detail: 'stale lease or invalid state transition' }, { status: 409 })
    }

    return NextResponse.json({ job_id: job.id, worker_status: job.worker_status, progress: job.progress })
}
