import { NextRequest, NextResponse } from 'next/server'
import { supabaseAdmin } from '@/lib/supabaseAdmin'
import { authenticateWorkerRequest, readJsonBodyWithLimit } from '@/lib/workerAuth'

export const dynamic = 'force-dynamic'

const LEASE_TTL_SECONDS = Number(process.env.AIRWORKER_LEASE_TTL_SECONDS || 300)

export async function POST(req: NextRequest, { params }: { params: { jobId: string } }) {
    const auth = await authenticateWorkerRequest(req)
    if (!auth.ok) return auth.response

    const bodyResult = await readJsonBodyWithLimit(req)
    if (!bodyResult.ok) return bodyResult.response
    const { lease_id, worker_instance_id } = bodyResult.body || {}
    if (!lease_id || !worker_instance_id) {
        return NextResponse.json({ error: 'invalid_request', detail: 'lease_id and worker_instance_id are required' }, { status: 400 })
    }

    const { data, error } = await supabaseAdmin.rpc('renew_worker_render_job_lease', {
        p_job_id: params.jobId,
        p_lease_id: lease_id,
        p_worker_instance_id: worker_instance_id,
        p_lease_ttl_seconds: LEASE_TTL_SECONDS,
    })

    if (error) return NextResponse.json({ error: 'db_error', detail: error.message }, { status: 500 })

    const job = Array.isArray(data) ? data[0] : data
    if (!job) {
        // stale lease (already expired/reassigned), wrong worker_instance_id, or job not in a renewable state
        return NextResponse.json({ error: 'lease_conflict', detail: 'lease is no longer active for this job' }, { status: 409 })
    }

    return NextResponse.json({ job_id: job.id, lease_id: job.lease_id, lease_expires_at: job.lease_expires_at })
}
