import { NextRequest, NextResponse } from 'next/server'
import { requireSuperAdmin, isAuthResponse } from '../_auth'
import { supabaseAdmin } from '@/lib/supabaseAdmin'
import { generateWorkerToken } from '@/lib/workerAuth'

export const dynamic = 'force-dynamic'

// [AIR-0227D Stage 4] Token issuance is admin-only and out-of-band from the
// worker - a worker can never mint its own token. Every list response
// omits token_hash entirely and only ever shows token_prefix, matching
// "로그에는 prefix 또는 token_id만 표시" from the task spec.
export async function GET(req: NextRequest) {
    const requester = await requireSuperAdmin(req)
    if (isAuthResponse(requester)) return requester

    const { data, error } = await supabaseAdmin
        .from('worker_tokens')
        .select('token_id, worker_id, token_prefix, allowed_job_types, capabilities, worker_group, issued_at, expires_at, revoked_at, last_used_at, created_by')
        .order('issued_at', { ascending: false })

    if (error) return NextResponse.json({ error: error.message }, { status: 500 })
    return NextResponse.json({ tokens: data || [] })
}

// [AIR-0227D Stage 4] One token per worker_id per call - "Worker별 개별
// 토큰, 전체 Worker 공용 토큰 금지" is enforced by requiring worker_id on
// every issuance (no "issue N tokens for a group" shortcut) rather than by
// a DB constraint, since revoking-and-reissuing under the same worker_id is
// a legitimate, expected flow (rotation).
export async function POST(req: NextRequest) {
    const requester = await requireSuperAdmin(req)
    if (isAuthResponse(requester)) return requester

    const body = await req.json().catch(() => ({}))
    const { worker_id, worker_group, allowed_job_types, capabilities, expires_in_days, revoke_existing } = body || {}

    if (!worker_id || typeof worker_id !== 'string') {
        return NextResponse.json({ error: 'worker_id is required' }, { status: 400 })
    }

    const { error: workerUpsertError } = await supabaseAdmin.from('workers').upsert(
        {
            worker_id,
            worker_group: typeof worker_group === 'string' ? worker_group : 'air-worker',
            allowed_job_types: Array.isArray(allowed_job_types) && allowed_job_types.length ? allowed_job_types : ['render_video'],
            capabilities: capabilities && typeof capabilities === 'object' ? capabilities : {},
            created_by: requester.user.email,
        },
        { onConflict: 'worker_id', ignoreDuplicates: false }
    )
    if (workerUpsertError) return NextResponse.json({ error: workerUpsertError.message }, { status: 500 })

    // Immediate revocation of prior tokens for this worker_id, so a rotation
    // is atomic-in-effect from the caller's point of view: the old token
    // stops working the moment the new one is returned, never both valid at
    // once for longer than this request takes.
    if (revoke_existing !== false) {
        await supabaseAdmin
            .from('worker_tokens')
            .update({ revoked_at: new Date().toISOString() })
            .eq('worker_id', worker_id)
            .is('revoked_at', null)
    }

    const issued = generateWorkerToken()
    const expiresAt = expires_in_days ? new Date(Date.now() + Number(expires_in_days) * 86400_000).toISOString() : null

    const { error: insertError } = await supabaseAdmin.from('worker_tokens').insert({
        token_id: issued.token_id,
        worker_id,
        token_hash: issued.token_hash,
        token_prefix: issued.token_prefix,
        allowed_job_types: Array.isArray(allowed_job_types) && allowed_job_types.length ? allowed_job_types : ['render_video'],
        capabilities: capabilities && typeof capabilities === 'object' ? capabilities : {},
        worker_group: typeof worker_group === 'string' ? worker_group : 'air-worker',
        expires_at: expiresAt,
        created_by: requester.user.email,
    })
    if (insertError) return NextResponse.json({ error: insertError.message }, { status: 500 })

    // raw_token is shown exactly once, in this response, and never persisted
    // or logged anywhere from this point on.
    return NextResponse.json({
        worker_id,
        token_id: issued.token_id,
        token: issued.raw_token,
        token_prefix: issued.token_prefix,
        expires_at: expiresAt,
        warning: 'This token will not be shown again. Store it securely now.',
    })
}
