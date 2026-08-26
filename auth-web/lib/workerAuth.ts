import crypto from 'crypto'
import { NextRequest, NextResponse } from 'next/server'
import { supabaseAdmin } from './supabaseAdmin'

// [AIR-0227D] Worker Token verification for the new /api/internal/worker/**
// routes. Mirrors the HMAC-opaque-token shape already used for desktop
// sessions (lib/desktopSession.ts) rather than inventing a new pattern, but
// tokens here are looked up by a public token_id prefix instead of being
// self-describing/signed - this lets a token be revoked/rotated by deleting
// or expiring its DB row alone (a signed token can't be invalidated before
// its own expiry without a revocation list; a stored-hash token can).
//
// Raw token shape: `awt_<token_id>_<secret>` where token_id is a public,
// non-secret lookup key (like a Stripe key prefix) and secret is the actual
// credential. Only token_hash = sha256(secret) is ever persisted - see
// migrations/air_0227d_worker_central_protocol.sql's worker_tokens table
// and docs/AIR_WORKER_CENTRAL_API.md.
//
// Long-lived tokens only for now (AIR-0227D scope) - see
// docs/AIR_WORKER_MIGRATION_PLAN.md for the documented short-lived-token
// migration path this is designed to not preclude (token_id/token_hash
// storage works unchanged for short-lived tokens too; only issuance would
// change).

const TOKEN_PREFIX = 'awt'
const MAX_BODY_BYTES = 256 * 1024 // 256KB - generous for job payload/error messages, well under Vercel's request body cap

export interface IssuedWorkerToken {
    raw_token: string // shown to the caller exactly once - never persisted, never logged
    token_id: string
    token_hash: string
    token_prefix: string
}

export function generateWorkerToken(): IssuedWorkerToken {
    const tokenId = crypto.randomBytes(9).toString('base64url') // ~12 chars, public
    const secret = crypto.randomBytes(32).toString('base64url') // ~43 chars, the actual credential
    const raw = `${TOKEN_PREFIX}_${tokenId}_${secret}`
    const tokenHash = crypto.createHash('sha256').update(secret).digest('hex')
    return {
        raw_token: raw,
        token_id: tokenId,
        token_hash: tokenHash,
        token_prefix: raw.slice(0, 12), // display-only, e.g. "awt_a1B2c3D4" - never enough to reconstruct the secret
    }
}

export interface AuthenticatedWorker {
    worker_id: string
    token_id: string
    allowed_job_types: string[]
    worker_group: string
    capabilities: Record<string, unknown>
}

// [AIR-0230] Hermes/topic_* jobs live in a separate table+RPC set
// (migrations/air_0230_hermes_worker_central_protocol.sql) from render jobs
// (air_0227d_worker_central_protocol.sql) - see that file's header for why
// (remote_render_queue.project_id is NOT NULL, topic jobs have no project).
// A worker/token is provisioned for exactly one family (its
// allowed_job_types is either all render_* or all topic_*/hermes types -
// see docs/AIR_0230_HERMES_BENCHMARK_WORKER_ARCHITECTURE.md §2b), so which
// RPC/table a request should use is derived from the AUTHENTICATED
// worker's allowed_job_types, never from the request body - same
// don't-trust-the-caller principle as allowed_job_types narrowing itself.
export const HERMES_JOB_TYPES = [
    'topic_research',
    'topic_benchmark_analyze',
    'music_trend_analyze',
    'music_prompt_pack_generate',
    'web_research',
    'script_plan_generate',
    'script_generate',
    'publish_metadata_generate',
]

export function isHermesWorker(worker: AuthenticatedWorker): boolean {
    return worker.allowed_job_types.some((t) => HERMES_JOB_TYPES.includes(t))
}

type AuthResult = { ok: true; worker: AuthenticatedWorker } | { ok: false; response: NextResponse }

function unauthorized(detail: string): AuthResult {
    // [AIR-0227D Stage 3] deliberately the same generic message/status for every
    // failure mode (missing header, malformed token, unknown token_id, hash
    // mismatch, revoked, expired) so a caller can't use error-message
    // differences to enumerate which part of a guessed token was wrong.
    return { ok: false, response: NextResponse.json({ error: 'unauthorized', detail }, { status: 401 }) }
}

export async function authenticateWorkerRequest(req: NextRequest): Promise<AuthResult> {
    const authHeader = req.headers.get('authorization') || ''
    // Bearer token ONLY - never accept a token via query string or body, so it
    // never lands in server access logs or browser history.
    const match = /^Bearer\s+(\S+)$/.exec(authHeader)
    if (!match) return unauthorized('missing_or_malformed_authorization_header')

    const raw = match[1]
    const parts = raw.split('_')
    if (parts.length < 3 || parts[0] !== TOKEN_PREFIX) return unauthorized('malformed_token')
    const tokenId = parts[1]
    const secret = parts.slice(2).join('_')

    const { data: row, error } = await supabaseAdmin
        .from('worker_tokens')
        .select('token_id, worker_id, token_hash, allowed_job_types, capabilities, worker_group, expires_at, revoked_at')
        .eq('token_id', tokenId)
        .maybeSingle()

    if (error || !row) return unauthorized('unknown_token')
    if (row.revoked_at) return unauthorized('revoked')
    if (row.expires_at && new Date(row.expires_at).getTime() < Date.now()) return unauthorized('expired')

    const suppliedHash = crypto.createHash('sha256').update(secret).digest()
    const storedHash = Buffer.from(row.token_hash, 'hex')
    if (suppliedHash.length !== storedHash.length || !crypto.timingSafeEqual(suppliedHash, storedHash)) {
        return unauthorized('hash_mismatch')
    }

    // Fire-and-forget last_used_at bump - never block/fail the request on this.
    void supabaseAdmin.from('worker_tokens').update({ last_used_at: new Date().toISOString() }).eq('token_id', tokenId)

    return {
        ok: true,
        worker: {
            worker_id: row.worker_id,
            token_id: row.token_id,
            allowed_job_types: row.allowed_job_types || ['render_video'],
            worker_group: row.worker_group || 'air-worker',
            capabilities: row.capabilities || {},
        },
    }
}

export async function readJsonBodyWithLimit(req: NextRequest): Promise<{ ok: true; body: any } | { ok: false; response: NextResponse }> {
    const text = await req.text()
    if (Buffer.byteLength(text, 'utf-8') > MAX_BODY_BYTES) {
        return { ok: false, response: NextResponse.json({ error: 'payload_too_large' }, { status: 413 }) }
    }
    try {
        return { ok: true, body: text ? JSON.parse(text) : {} }
    } catch {
        return { ok: false, response: NextResponse.json({ error: 'invalid_json' }, { status: 400 }) }
    }
}

// [AIR-0227D Stage 10] normalized-payload hash for idempotency-key conflict
// detection - independent of key order, since JSON.stringify on two
// differently-constructed-but-equal objects can disagree on key order.
export function hashIdempotentPayload(payload: unknown): string {
    const normalize = (v: unknown): unknown => {
        if (Array.isArray(v)) return v.map(normalize)
        if (v && typeof v === 'object') {
            return Object.keys(v as Record<string, unknown>)
                .sort()
                .reduce((acc, k) => {
                    acc[k] = normalize((v as Record<string, unknown>)[k])
                    return acc
                }, {} as Record<string, unknown>)
        }
        return v
    }
    return crypto.createHash('sha256').update(JSON.stringify(normalize(payload))).digest('hex')
}

// [AIR-0227D Stage 10] Shared by the complete and fail routes - identical
// idempotency/lease-conflict handling, differing only in p_success and
// which fields are relevant. Idempotency-Key is a REQUIRED header (not
// caller-optional) precisely because retries after a lost response are the
// whole point - see docs/AIR_WORKER_LEASE_PROTOCOL.md.
export async function reportJobOutcome(
    req: NextRequest,
    jobId: string,
    success: boolean
): Promise<NextResponse> {
    const auth = await authenticateWorkerRequest(req)
    if (!auth.ok) return auth.response

    const idempotencyKey = req.headers.get('idempotency-key')
    if (!idempotencyKey) {
        return NextResponse.json({ error: 'invalid_request', detail: 'Idempotency-Key header is required' }, { status: 400 })
    }

    const bodyResult = await readJsonBodyWithLimit(req)
    if (!bodyResult.ok) return bodyResult.response
    const { lease_id, worker_instance_id, output_ref, result_payload, error_code, error_message } = bodyResult.body || {}
    if (!lease_id || !worker_instance_id) {
        return NextResponse.json({ error: 'invalid_request', detail: 'lease_id and worker_instance_id are required' }, { status: 400 })
    }
    if (success && (!output_ref || typeof output_ref !== 'string')) {
        return NextResponse.json({ error: 'invalid_request', detail: 'output_ref is required on complete' }, { status: 400 })
    }

    const requestHash = hashIdempotentPayload({ jobId, lease_id, worker_instance_id, success, output_ref, result_payload, error_code, error_message })

    // [AIR-0230] result_payload is render-irrelevant (undefined) on that
    // path - report_worker_render_job_outcome has no matching param, so it
    // must not be passed to that RPC call at all.
    const hermes = isHermesWorker(auth.worker)
    const { data, error } = await supabaseAdmin.rpc(
        hermes ? 'report_worker_hermes_job_outcome' : 'report_worker_render_job_outcome',
        {
            p_job_id: jobId,
            p_lease_id: lease_id,
            p_worker_instance_id: worker_instance_id,
            p_worker_id: auth.worker.worker_id,
            p_success: success,
            p_idempotency_key: idempotencyKey,
            p_request_hash: requestHash,
            p_result_reference: typeof output_ref === 'string' ? output_ref : null,
            ...(hermes ? { p_result_payload: result_payload ?? null } : {}),
            p_error_code: typeof error_code === 'string' ? error_code : null,
            p_error_message: typeof error_message === 'string' ? error_message.slice(0, 2000) : null,
        }
    )

    if (error) return NextResponse.json({ error: 'db_error', detail: error.message }, { status: 500 })

    const outcome = data as { outcome: string; http_status: number; [k: string]: unknown }
    return NextResponse.json(outcome, { status: outcome?.http_status || 500 })
}

export async function logWorkerAuditEvent(params: {
    job_id?: string | null
    worker_id?: string | null
    worker_instance_id?: string | null
    event_type: string
    from_status?: string | null
    to_status?: string | null
    lease_id?: string | null
    detail?: Record<string, unknown>
}) {
    // Best-effort - an audit-log write failure must never fail the caller's
    // actual request. Most write paths already log via the RPC functions
    // themselves (see migrations/air_0227d_worker_central_protocol.sql); this
    // is only used for events the RPCs can't see (e.g. auth rejections,
    // register/heartbeat which don't touch remote_render_queue at all).
    try {
        await supabaseAdmin.from('worker_job_events').insert({
            job_id: params.job_id ?? null,
            worker_id: params.worker_id ?? null,
            worker_instance_id: params.worker_instance_id ?? null,
            event_type: params.event_type,
            from_status: params.from_status ?? null,
            to_status: params.to_status ?? null,
            lease_id: params.lease_id ?? null,
            detail: params.detail ?? {},
        })
    } catch (e) {
        console.warn('[workerAuth] audit log insert failed (non-fatal):', e)
    }
}
