import { NextRequest, NextResponse } from 'next/server'
import { supabaseAdmin } from '@/lib/supabaseAdmin'
import { authenticateWorkerRequest, readJsonBodyWithLimit } from '@/lib/workerAuth'

export const dynamic = 'force-dynamic'

// [AIR-0227D Stage 3] Worker-level liveness only - distinct from a job
// lease's heartbeat_at (updated by claim/renew/progress). A worker with no
// active job still calls this periodically so the admin UI can show
// online/offline without inferring it from job activity alone.
export async function POST(req: NextRequest) {
    const auth = await authenticateWorkerRequest(req)
    if (!auth.ok) return auth.response

    const bodyResult = await readJsonBodyWithLimit(req)
    if (!bodyResult.ok) return bodyResult.response
    const { worker_instance_id } = bodyResult.body || {}
    if (!worker_instance_id || typeof worker_instance_id !== 'string') {
        return NextResponse.json({ error: 'invalid_request', detail: 'worker_instance_id is required' }, { status: 400 })
    }

    const { error } = await supabaseAdmin
        .from('workers')
        .update({ last_worker_instance_id: worker_instance_id, last_heartbeat_at: new Date().toISOString() })
        .eq('worker_id', auth.worker.worker_id)

    if (error) return NextResponse.json({ error: 'db_error', detail: error.message }, { status: 500 })
    return NextResponse.json({ ok: true, server_time: new Date().toISOString() })
}
