import { NextRequest, NextResponse } from 'next/server'
import { requireAdmin, isAuthResponse } from '../_auth'
import { supabaseAdmin } from '@/lib/supabaseAdmin'

export const dynamic = 'force-dynamic'

// [AIR-0227D Stage 16] Minimal admin visibility - deliberately just enough
// to QA staging (worker list, online/offline, current lease, token revoked
// state, retry/error info), not a full operations dashboard. Follows the
// existing admin/render-queue GET pattern (flat list, no pagination UI yet).
const ONLINE_THRESHOLD_SECONDS = 60 // worker considered offline if no heartbeat within this window

export async function GET(req: NextRequest) {
    const requester = await requireAdmin(req)
    if (isAuthResponse(requester)) return requester

    const [{ data: workers, error: workersError }, { data: tokens, error: tokensError }, { data: activeJobs, error: jobsError }] = await Promise.all([
        supabaseAdmin.from('workers').select('*').order('registered_at', { ascending: false }),
        supabaseAdmin.from('worker_tokens').select('token_id, worker_id, token_prefix, revoked_at, expires_at, last_used_at').order('issued_at', { ascending: false }),
        supabaseAdmin
            .from('remote_render_queue')
            .select('id, worker_id, worker_instance_id, worker_status, status, progress, retry_count, error_code, error_message, lease_expires_at')
            .not('worker_id', 'is', null)
            .in('status', ['rendering']),
    ])

    if (workersError) return NextResponse.json({ error: workersError.message }, { status: 500 })
    if (tokensError) return NextResponse.json({ error: tokensError.message }, { status: 500 })
    if (jobsError) return NextResponse.json({ error: jobsError.message }, { status: 500 })

    const now = Date.now()
    const jobsByWorker = new Map<string, any>()
    for (const job of activeJobs || []) {
        // last-write-wins if a worker somehow has >1 active job row (shouldn't happen, but this is a display endpoint, not an invariant enforcer)
        jobsByWorker.set(job.worker_id, job)
    }
    const tokensByWorker = new Map<string, any[]>()
    for (const t of tokens || []) {
        const list = tokensByWorker.get(t.worker_id) || []
        list.push(t)
        tokensByWorker.set(t.worker_id, list)
    }

    const result = (workers || []).map((w) => {
        const lastHeartbeat = w.last_heartbeat_at ? new Date(w.last_heartbeat_at).getTime() : null
        const online = lastHeartbeat !== null && now - lastHeartbeat < ONLINE_THRESHOLD_SECONDS * 1000
        const currentJob = jobsByWorker.get(w.worker_id) || null
        const workerTokens = tokensByWorker.get(w.worker_id) || []
        const activeToken = workerTokens.find((t) => !t.revoked_at && (!t.expires_at || new Date(t.expires_at).getTime() > now))

        return {
            worker_id: w.worker_id,
            worker_group: w.worker_group,
            allowed_job_types: w.allowed_job_types,
            online,
            last_heartbeat_at: w.last_heartbeat_at,
            token_revoked: !activeToken,
            token_prefix: activeToken?.token_prefix ?? null,
            current_job: currentJob
                ? {
                      job_id: currentJob.id,
                      worker_status: currentJob.worker_status,
                      status: currentJob.status,
                      progress: currentJob.progress,
                      retry_count: currentJob.retry_count,
                      error_code: currentJob.error_code,
                      lease_expires_at: currentJob.lease_expires_at,
                  }
                : null,
        }
    })

    return NextResponse.json({ workers: result })
}
