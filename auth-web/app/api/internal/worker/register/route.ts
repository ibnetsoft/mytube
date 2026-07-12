import { NextRequest, NextResponse } from 'next/server'
import { supabaseAdmin } from '@/lib/supabaseAdmin'
import { authenticateWorkerRequest, readJsonBodyWithLimit, logWorkerAuditEvent } from '@/lib/workerAuth'

export const dynamic = 'force-dynamic'

// [AIR-0227D Stage 3] Idempotent upsert - a worker calls this once per
// Manager process start. Does NOT create the worker_tokens row (tokens are
// issued out-of-band by an admin, never self-registered) - this only
// records/refreshes the workers registry row so the admin UI can show
// "known workers" even before their first job claim.
export async function POST(req: NextRequest) {
    const auth = await authenticateWorkerRequest(req)
    if (!auth.ok) return auth.response

    const bodyResult = await readJsonBodyWithLimit(req)
    if (!bodyResult.ok) return bodyResult.response
    const { worker_instance_id, capabilities } = bodyResult.body || {}

    if (!worker_instance_id || typeof worker_instance_id !== 'string') {
        return NextResponse.json({ error: 'invalid_request', detail: 'worker_instance_id is required' }, { status: 400 })
    }

    const { worker } = auth
    const { error } = await supabaseAdmin.from('workers').upsert(
        {
            worker_id: worker.worker_id,
            worker_group: worker.worker_group,
            allowed_job_types: worker.allowed_job_types,
            capabilities: capabilities && typeof capabilities === 'object' ? capabilities : worker.capabilities,
            last_worker_instance_id: worker_instance_id,
            last_heartbeat_at: new Date().toISOString(),
        },
        { onConflict: 'worker_id' }
    )

    if (error) {
        return NextResponse.json({ error: 'db_error', detail: error.message }, { status: 500 })
    }

    await logWorkerAuditEvent({
        worker_id: worker.worker_id,
        worker_instance_id,
        event_type: 'register',
    })

    return NextResponse.json({
        worker_id: worker.worker_id,
        allowed_job_types: worker.allowed_job_types,
        worker_group: worker.worker_group,
    })
}
