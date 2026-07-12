import { NextRequest, NextResponse } from 'next/server'
import { supabaseAdmin } from '@/lib/supabaseAdmin'
import { authenticateWorkerRequest, readJsonBodyWithLimit, logWorkerAuditEvent } from '@/lib/workerAuth'

export const dynamic = 'force-dynamic'

// [AIR-0227D Stage 6] Server-config lease TTL, not caller-suppliable - a
// malicious/buggy worker could otherwise request an absurdly long lease and
// starve reassignment. See docs/AIR_WORKER_CENTRAL_API.md for the tuning
// discussion; env override exists purely for staging experimentation.
const LEASE_TTL_SECONDS = Number(process.env.AIRWORKER_LEASE_TTL_SECONDS || 300)

// [AIR-0227D Stage 4/6] allowed_job_types and worker_group come from the
// AUTHENTICATED token record (auth.worker), never from the request body -
// the task payload's job_type/priority/tenant_id are read FROM the queue
// row the RPC picks, never trusted from the worker's claim request either.
// This is the "don't trust worker-supplied tenant_id/priority/ownership/
// allowed job_type" principle from the task spec, enforced structurally:
// the claim body is only used to optionally narrow (not widen) the
// authenticated allowed_job_types.
export async function POST(req: NextRequest) {
    const auth = await authenticateWorkerRequest(req)
    if (!auth.ok) return auth.response

    const bodyResult = await readJsonBodyWithLimit(req)
    if (!bodyResult.ok) return bodyResult.response
    const { worker_instance_id, requested_job_types } = bodyResult.body || {}

    if (!worker_instance_id || typeof worker_instance_id !== 'string') {
        return NextResponse.json({ error: 'invalid_request', detail: 'worker_instance_id is required' }, { status: 400 })
    }

    const { worker } = auth
    let allowedJobTypes = worker.allowed_job_types
    if (Array.isArray(requested_job_types) && requested_job_types.every((t) => typeof t === 'string')) {
        // narrow-only: intersect, never widen beyond what the token actually allows
        allowedJobTypes = worker.allowed_job_types.filter((t) => requested_job_types.includes(t))
    }
    if (allowedJobTypes.length === 0) {
        return NextResponse.json({ error: 'invalid_request', detail: 'no overlapping job_type between token and request' }, { status: 400 })
    }

    const { data, error } = await supabaseAdmin.rpc('claim_worker_render_job', {
        p_worker_id: worker.worker_id,
        p_worker_instance_id: worker_instance_id,
        p_allowed_job_types: allowedJobTypes,
        p_worker_group: worker.worker_group,
        p_lease_ttl_seconds: LEASE_TTL_SECONDS,
    })

    if (error) {
        return NextResponse.json({ error: 'db_error', detail: error.message }, { status: 500 })
    }

    const job = Array.isArray(data) ? data[0] : data
    if (!job) {
        return NextResponse.json({ job: null })
    }

    return NextResponse.json({
        job_id: job.id,
        job_type: job.job_type,
        priority: job.priority,
        tenant_id: job.tenant_id,
        payload: {
            project_id: job.project_id,
            project_name: job.project_name,
            asset_file_id: job.asset_file_id,
            asset_file_name: job.asset_file_name,
            metadata: job.metadata,
        },
        lease_id: job.lease_id,
        lease_expires_at: job.lease_expires_at,
        attempt_number: job.attempt_number,
    })
}
